const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

module.exports = {
  entry: {
    'service-worker': './src/background/service-worker.js',
    sidepanel: './src/sidepanel/sidepanel.js',
    'content-script': './src/content/content-script.js',
    offscreen: './src/offscreen/offscreen.js',
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].js',
    clean: true,
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        { from: 'manifest.json', to: 'manifest.json' },
        { from: 'src/sidepanel/sidepanel.html', to: 'sidepanel.html' },
        { from: 'src/sidepanel/sidepanel.css', to: 'sidepanel.css' },
        { from: 'src/offscreen/offscreen.html', to: 'offscreen.html' },
        { from: 'src/assets', to: 'assets' },
      ],
    }),
  ],
  resolve: {
    extensions: ['.js'],
  },
  devtool: process.env.NODE_ENV === 'development' ? 'cheap-module-source-map' : false,
};
