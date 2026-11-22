const path = require('path');
const fs = require('fs');
const { build } = require('esbuild');

const lucidePath = path.resolve(__dirname, '../node_modules/lucide-react/dist/cjs/lucide-react.js');
console.log('Building production bundle with esbuild...');
const t0 = Date.now();

const distDir = path.resolve(__dirname, '../dist');
const distAssetsDir = path.resolve(distDir, 'assets');
const staticDir = path.resolve(__dirname, '../static');
const staticAssetsDir = path.resolve(staticDir, 'assets');

// Ensure output directories exist
if (!fs.existsSync(distAssetsDir)) {
  fs.mkdirSync(distAssetsDir, { recursive: true });
}

// Copy static template assets into dist
if (fs.existsSync(path.resolve(staticDir, 'index.html'))) {
  fs.copyFileSync(path.resolve(staticDir, 'index.html'), path.resolve(distDir, 'index.html'));
}
if (fs.existsSync(path.resolve(staticDir, 'favicon.svg'))) {
  fs.copyFileSync(path.resolve(staticDir, 'favicon.svg'), path.resolve(distDir, 'favicon.svg'));
}
if (fs.existsSync(path.resolve(staticAssetsDir, 'index-DfsM8HI2.css'))) {
  fs.copyFileSync(path.resolve(staticAssetsDir, 'index-DfsM8HI2.css'), path.resolve(distAssetsDir, 'index-DfsM8HI2.css'));
}

build({
  entryPoints: [path.resolve(__dirname, '../src/main.tsx')],
  bundle: true,
  outfile: path.resolve(__dirname, '../dist/assets/index-CnOmatPM.js'),
  format: 'esm',
  jsx: 'automatic',
  loader: { '.css': 'empty' },
  minify: true,
  define: {
    'process.env.NODE_ENV': '"production"',
    'import.meta.env.VITE_API_BASE_URL': '"/api/v1"',
  },
  alias: {
    'lucide-react': lucidePath,
  },
})
  .then(() => {
    console.log(`Build completed successfully in ${Date.now() - t0} ms.`);
  })
  .catch((err) => {
    console.error('Build failed:', err);
    process.exit(1);
  });
