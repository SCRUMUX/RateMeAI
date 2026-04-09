const coreConfig = require('../AICADS-/packages/core/config/tailwind/tailwind.config.cjs');

/** @type {import('tailwindcss').Config} */
module.exports = {
  ...coreConfig,
  content: {
    relative: true,
    files: [
      './src/**/*.{js,ts,jsx,tsx}',
      './index.html',
      '../AICADS-/packages/core/components/**/*.{js,ts,jsx,tsx}',
    ],
  },
  darkMode: ['class', '[data-theme="dark"]'],
};
