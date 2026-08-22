const path = require('path');
const fs = require('fs');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const {DefinePlugin} = require('webpack');

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
            new ScratchSecurityPatchPlugin()
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
