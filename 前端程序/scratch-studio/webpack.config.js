const path = require('path');
const fs = require('fs');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const {DefinePlugin} = require('webpack');
const {repaintScratchPurple, findResidualPurple} = require('./scripts/brand-palette.cjs');

/**
 * @scratch/scratch-gui 的 npm 包不仅有 JS 入口，还会在运行时按相对路径加载
 * static/（Blockly 图标）、chunks/（教程等懒加载代码）和 libraries/。
 * 不额外引入 CopyWebpackPlugin，直接把这些官方运行资源作为 webpack 资产发射，
 * 这样开发服务器和生产 dist 的路径保持一致。
 */
class ScratchGuiAssetsPlugin {
    apply (compiler) {
        const guiDist = path.resolve(
            __dirname,
            'node_modules/@scratch/scratch-gui/dist'
        );
        const copyDirectory = (compilation, root, relativeRoot) => {
            // Some published scratch-gui versions omit optional runtime
            // directories. Treat those as absent instead of letting
            // readdirSync abort the whole compilation with ENOENT.
            if (!fs.existsSync(root)) {
                compilation.warnings.push(
                    new Error(`scratch-gui runtime directory not found: ${path.relative(__dirname, root)}`)
                );
                return;
            }
            for (const entry of fs.readdirSync(root, {withFileTypes: true})) {
                const relativePath = path.posix.join(relativeRoot, entry.name);
                const fullPath = path.join(root, entry.name);
                if (entry.isDirectory()) {
                    copyDirectory(compilation, fullPath, relativePath);
                } else if (!entry.name.endsWith('.map')) {
                    compilation.emitAsset(
                        relativePath,
                        new compiler.webpack.sources.RawSource(fs.readFileSync(fullPath))
                    );
                }
            }
        };

        compiler.hooks.thisCompilation.tap('ScratchGuiAssetsPlugin', compilation => {
            compilation.hooks.processAssets.tap(
                {
                    name: 'ScratchGuiAssetsPlugin',
                    stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_ADDITIONAL
                },
                () => {
                    for (const directory of ['static', 'chunks', 'libraries']) {
                        copyDirectory(compilation, path.join(guiDist, directory), directory);
                    }
                    // Scratch VM 的扩展 worker 也由 GUI 在浏览器中按文件名加载。
                    for (const filename of ['extension-worker.js', '30d09ba32a17082ef820b57d52d60b7b.hex']) {
                        const source = path.join(guiDist, filename);
                        if (fs.existsSync(source)) {
                            compilation.emitAsset(
                                filename,
                                new compiler.webpack.sources.RawSource(fs.readFileSync(source))
                            );
                        }
                    }
                }
            );
        });
    }
}

/**
 * 平台扩展的产出：`src/extensions/<ID>.js` → 资产 `<ID>`（**故意不带后缀**）。
 *
 * 为什么名字必须正好等于作品内 ID：`.sb3` 只记扩展 ID、不记它从哪儿加载
 * （`scratch-vm/src/serialization/sb3.js:355` 官方注释：将来若支持按 URL 加载…，
 * 即现在不支持），所以重开作品时 VM 拿 ID 当相对路径去 `importScripts`，
 * 实测请求的正是 `<Studio base>/<ID>`。名字对不上，历史作品就打不开。
 *
 * 每个产物 = `_shim.js` + 扩展体。垫片只此一份，各扩展不许自带副本。
 */
const EXTENSIONS_DIR = path.resolve(__dirname, 'src/extensions');

function readPlatformExtensions () {
    if (!fs.existsSync(EXTENSIONS_DIR)) return [];
    const shim = fs.readFileSync(path.join(EXTENSIONS_DIR, '_shim.js'), 'utf8');
    return fs.readdirSync(EXTENSIONS_DIR)
        .filter(name => name.endsWith('.js') && !name.startsWith('_'))
        .map(name => ({
            id: name.replace(/\.js$/, ''),
            // dev 下每次请求重新拼，改扩展不用重启
            build: () => `${shim}\n${fs.readFileSync(path.join(EXTENSIONS_DIR, name), 'utf8')}`
        }));
}

class PlatformExtensionsPlugin {
    apply (compiler) {
        compiler.hooks.thisCompilation.tap('PlatformExtensionsPlugin', compilation => {
            compilation.hooks.processAssets.tap(
                {
                    name: 'PlatformExtensionsPlugin',
                    stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_ADDITIONAL
                },
                () => {
                    for (const ext of readPlatformExtensions()) {
                        compilation.emitAsset(
                            ext.id,
                            new compiler.webpack.sources.RawSource(ext.build())
                        );
                    }
                }
            );
        });
    }
}

const HULL_FORMAT_REPLACEMENTS = [
    [
        /new Function\("pt","return \[pt"\+t\[0\]\+",pt"\+t\[1\]\+"\];"\)\(e\)/g,
        '[e[t[0].slice(1)], e[t[1].slice(1)]]'
    ],
    [
        /new Function\("pt","var o = \{\}; o"\+t\[0\]\+"= pt\[0\]; o"\+t\[1\]\+"= pt\[1\]; return o;"\)\(e\)/g,
        '((o) => { o[t[0].slice(1)] = e[0]; o[t[1].slice(1)] = e[1]; return o; })({})'
    ]
];

class ScratchSecurityPatchPlugin {
    apply (compiler) {
        compiler.hooks.thisCompilation.tap('ScratchSecurityPatchPlugin', compilation => {
            compilation.hooks.processAssets.tap(
                {
                    name: 'ScratchSecurityPatchPlugin',
                    // Run after webpack's minimizer so the checked asset is the
                    // exact browser artifact that will be deployed.
                    stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_SUMMARIZE
                },
                assets => {
                    for (const [filename, asset] of Object.entries(assets)) {
                        if (!filename.endsWith('.js') && !filename.endsWith('.map')) continue;
                        let source = asset.source().toString();
                        for (const [pattern, replacement] of HULL_FORMAT_REPLACEMENTS) {
                            source = source.replace(pattern, replacement);
                        }
                        compilation.updateAsset(
                            filename,
                            new compiler.webpack.sources.RawSource(source)
                        );
                    }
                    const residual = /new Function\(["']pt["']/;
                    for (const [filename, asset] of Object.entries(compilation.getAssets())) {
                        if ((filename.endsWith('.js') || filename.endsWith('.map'))
                            && residual.test(asset.source.source().toString())) {
                            throw new Error(`Unsafe hull.js dynamic formatter remains in ${filename}`);
                        }
                    }
                }
            );
        });
    }
}

/**
 * 修掉 scratch-gui 产物里被硬编码的**嵌套** publicPath。
 *
 * dist 里有第二个 webpack runtime（打包 scratch-storage 时留下的），它的
 * `.p` 是写死的 `"/"`，只用来起 scratch-storage 的取数 worker：
 *
 *     __nested_webpack_require_108080__.p = "/"
 *     __nested_webpack_require_108080__.u = e => "chunks/fetch-worker.<hash>.js"
 *
 * Studio 挂在主站 `/scratch-studio/` 下时，这条请求打到**站点根**，被 Vue 的 SPA
 * history fallback 接走 → 回来 index.html → worker 里 `Unexpected token '<'`。
 * 素材的字节全靠这个 worker 拉，它起不来，`storage.load()` 就永远不 settle：
 * 素材库能开、缩略图能显示（走 cdn 绝对地址，不经这条路），**点了却什么都不发生**，
 * 且不报错。完整现场与实测见 `src/gui/publicPath.js` 头注。
 *
 * 改成读一个自己声明的全局，值由 `src/gui/publicPath.js` 在启动时写入。
 * 与安全补丁 / 品牌调色同一个 hook、同一个 stage：改的就是最终发给浏览器的字节。
 */
const NESTED_PUBLIC_PATH = /(__nested_webpack_require_\d+__)\.p\s*=\s*["']\/["']/g;
// 开发模式的 eval-source-map 把依赖源码包进 JS 字符串，字符串内的引号会变成
// `\"`。不能把它与生产形式混成同一个替换：写回未转义的 `"/"` 会直接破坏 eval。
const NESTED_PUBLIC_PATH_ESCAPED = /(__nested_webpack_require_\d+__)\.p\s*=\s*\\["']\/\\["']/g;
const NESTED_PUBLIC_PATH_FIXED = /__nested_webpack_require_\d+__\.p\s*=\s*\(self\.__STUDIO_PUBLIC_PATH__\|\|\\?["']\/\\?["']\)/;
const NESTED_PUBLIC_PATH_REPLACEMENTS = [
    [NESTED_PUBLIC_PATH, '$1.p=(self.__STUDIO_PUBLIC_PATH__||"/")'],
    [NESTED_PUBLIC_PATH_ESCAPED, '$1.p=(self.__STUDIO_PUBLIC_PATH__||\\"/\\")']
];

class NestedPublicPathPlugin {
    apply (compiler) {
        compiler.hooks.thisCompilation.tap('NestedPublicPathPlugin', compilation => {
            compilation.hooks.processAssets.tap(
                {
                    name: 'NestedPublicPathPlugin',
                    stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_SUMMARIZE
                },
                assets => {
                    let patched = 0;
                    let sawWorker = false;
                    let alreadyPatched = false;
                    for (const [filename, asset] of Object.entries(assets)) {
                        if (!filename.endsWith('.js')) continue;
                        const source = asset.source().toString();
                        if (source.includes('chunks/fetch-worker.')) sawWorker = true;
                        if (NESTED_PUBLIC_PATH_FIXED.test(source)) alreadyPatched = true;
                        const fixed = NESTED_PUBLIC_PATH_REPLACEMENTS.reduce(
                            (next, [pattern, replacement]) => next.replace(pattern, replacement),
                            source
                        );
                        if (fixed === source) continue;
                        patched += 1;
                        compilation.updateAsset(
                            filename,
                            new compiler.webpack.sources.RawSource(fixed)
                        );
                    }
                    // 升级 scratch-gui 后官方若换了写法，这条补丁会静默失效，
                    // 症状是「素材库点了没反应」——那是最难从现象猜回来的一类 bug。
                    // 宁可让构建停下来。
                    if (sawWorker && patched === 0 && !alreadyPatched) {
                        throw new Error(
                            'scratch-gui 的嵌套 publicPath 没被改写：产物里仍有 ' +
                            'chunks/fetch-worker，却匹配不到 `__nested_webpack_require_*__.p="/"`。' +
                            '检查 NestedPublicPathPlugin 的正则（见 src/gui/publicPath.js 头注）'
                        );
                    }
                }
            );
        });
    }
}

/**
 * 品牌调色：把产物里的官方紫换成平台主色。替换表与理由见
 * `scripts/brand-palette.cjs`（含"积木配色不许动"的哨兵）。
 *
 * 与 ScratchSecurityPatchPlugin 同一个 hook、同一个 stage：产物已经过压缩，
 * 改的就是最终发给浏览器的那份字节。懒加载的 `chunks/*.js` 也在资产表里，
 * 造型/声音编辑器点开时才插入的那批样式一并覆盖到。
 */
class BrandPalettePlugin {
    apply (compiler) {
        compiler.hooks.thisCompilation.tap('BrandPalettePlugin', compilation => {
            compilation.hooks.processAssets.tap(
                {
                    name: 'BrandPalettePlugin',
                    stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_SUMMARIZE
                },
                assets => {
                    for (const [filename, asset] of Object.entries(assets)) {
                        if (!filename.endsWith('.js') && !filename.endsWith('.map')) continue;
                        const source = asset.source().toString();
                        const painted = repaintScratchPurple(source);
                        if (painted === source) continue;
                        compilation.updateAsset(
                            filename,
                            new compiler.webpack.sources.RawSource(painted)
                        );
                    }
                    // 漏网即报错：升级后官方换了写法（比如改用 CSS 变量或别的紫），
                    // 界面会悄悄花掉一半。宁可让构建停下来。
                    for (const [filename, asset] of Object.entries(compilation.getAssets())) {
                        if (!filename.endsWith('.js') && !filename.endsWith('.map')) continue;
                        const residual = findResidualPurple(asset.source.source().toString());
                        if (residual) {
                            throw new Error(
                                `Scratch 官方紫未被替换：${residual}（${filename}）——` +
                                '检查 scripts/brand-palette.cjs 的替换表'
                            );
                        }
                    }
                }
            );
        });
    }
}

module.exports = (env, argv) => {
    const isDev = argv.mode !== 'production';

    return {
        entry: './src/index.jsx',
        output: {
            path: path.resolve(__dirname, 'dist'),
            filename: 'studio.[contenthash].js',
            publicPath: 'auto',
            clean: true
        },
        resolve: {
            extensions: ['.js', '.jsx', '.json']
        },
        module: {
            rules: [
                {
                    test: /\.jsx?$/,
                    exclude: /node_modules/,
                    use: {
                        loader: 'babel-loader',
                        options: {
                            presets: [
                                ['@babel/preset-env', {targets: 'defaults'}],
                                ['@babel/preset-react', {runtime: 'automatic'}]
                            ]
                        }
                    }
                }
            ]
        },
        plugins: [
            // Webpack 5 不再自动给浏览器注入 Node 的 `process`。
            // 只把这个布尔配置在构建期替换，运行时不访问 process.env，避免 Studio 白屏。
            // 也认 `--env mock`：设环境变量的写法在 PowerShell / bash / CI 各不相同，
            // 一个跨平台都能用的开关省掉一整类"我这边跑不起来"。
            new DefinePlugin({
                __STUDIO_USE_MOCK__: JSON.stringify(
                    Boolean(env && env.mock) || process.env.STUDIO_USE_MOCK === '1'
                )
            }),
            new HtmlWebpackPlugin({
                template: './index.html'
            }),
            new ScratchGuiAssetsPlugin(),
            new PlatformExtensionsPlugin(),
            new ScratchSecurityPatchPlugin(),
            new NestedPublicPathPlugin(),
            new BrandPalettePlugin()
        ],
        devServer: {
            port: 8602,
            hot: true,
            historyApiFallback: true,
            // 同域联调：把 /api 代理到本地 FastAPI（默认 8000），真实接口模式用
            proxy: [
                {
                    context: ['/api'],
                    target: 'http://127.0.0.1:8000',
                    changeOrigin: true
                }
            ],
            client: {overlay: true},
            // 平台扩展的产物没有 `.js` 后缀（名字必须等于作品内 ID），静态中间件
            // 给不出正确的 MIME，而浏览器对 `importScripts` 的类型有要求；再加上
            // `historyApiFallback: true` 会把 `/wpmStringV1` 当路由发回 index.html。
            // 所以这些路径必须**抢在**兜底之前自己回，并显式声明类型。
            // 生产由 nginx 承担同一件事（见《51、Scratch 扩展接入方案》§4）。
            setupMiddlewares: (middlewares) => {
                for (const ext of readPlatformExtensions()) {
                    middlewares.unshift({
                        name: `platform-extension-${ext.id}`,
                        path: `/${ext.id}`,
                        middleware: (req, res) => {
                            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
                            res.setHeader('Cache-Control', 'no-store');
                            res.end(ext.build());
                        }
                    });
                }
                return middlewares;
            }
        },
        devtool: isDev ? 'eval-source-map' : 'source-map'
    };
};
