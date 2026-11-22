const path = require('path');
const { build } = require('esbuild');

const lucidePath = path.resolve(__dirname, '../node_modules/lucide-react/dist/cjs/lucide-react.js');
console.log('Building production bundle with esbuild...');
const t0 = Date.now();

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
    'import.meta.env.VITE_API_BASE_URL': '"http://localhost:8000/api/v1"',
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
