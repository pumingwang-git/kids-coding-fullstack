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
            new ScratchGuiAssetsPlugin()
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
            client: {overlay: true}
        },
        devtool: isDev ? 'eval-source-map' : 'source-map'
    };
};
