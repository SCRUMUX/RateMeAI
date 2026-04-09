const coreConfig = require('./tailwind-core.config.cjs');

/** @type {import('tailwindcss').Config} */
module.exports = {
  ...coreConfig,
  content: {
    relative: true,
    files: [
      './src/**/*.{js,ts,jsx,tsx}',
      './index.html',
    ],
  },
  darkMode: ['class', '[data-theme="dark"]'],
};
