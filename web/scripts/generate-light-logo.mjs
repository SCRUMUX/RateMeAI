/**
 * generate-light-logo.mjs (1.36.0)
 *
 * Один разовый build-time скрипт. Читает src/assets/logo.png
 * (оптимизированный под dark theme — белый/светлый текст и
 * cyan-glow на тёмной подложке) и генерирует
 * src/assets/logo-light.png — версию для светлой темы.
 *
 * Алгоритм: luminance-only inversion с сохранением hue.
 *  - Считаем перцептивную яркость L = 0.299r + 0.587g + 0.114b.
 *  - Инвертируем L → L' = 255 - L.
 *  - Восстанавливаем RGB, сохранив относительные пропорции каналов
 *    (chroma direction). Это значит, что cyan-glow (g+b dominant)
 *    остаётся cyan, но яркость "перевёрнута": светлый текст
 *    становится тёмным, тёмная подложка — светлой.
 *  - Альфа-канал не трогаем (preserve transparency / glow halo).
 *
 * Запуск: cd web && npm run generate:light-logo
 *
 * Идемпотентный: повторный запуск даёт байт-в-байт тот же результат.
 * Скрипт коммитится в репозиторий вместе с logo-light.png — re-run
 * нужен только при обновлении исходного logo.png.
 */
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Jimp } from 'jimp';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const SRC = path.join(projectRoot, 'src', 'assets', 'logo.png');
const OUT = path.join(projectRoot, 'src', 'assets', 'logo-light.png');

console.log(`[gen-light-logo] reading ${SRC}`);
const img = await Jimp.read(SRC);
console.log(`[gen-light-logo] dimensions ${img.bitmap.width}x${img.bitmap.height}`);

const data = img.bitmap.data;
for (let i = 0; i < data.length; i += 4) {
  const r = data[i];
  const g = data[i + 1];
  const b = data[i + 2];
  // Alpha untouched.

  // Perceptual luminance (Rec. 601 — gives brand-cyan slightly more
  // weight than naive average, which preserves brand identity better).
  const L = 0.299 * r + 0.587 * g + 0.114 * b;
  if (L < 1) continue; // pure black / fully transparent backdrop

  const Lnew = 255 - L;
  const ratio = Lnew / L;

  // Scale RGB by inverse luminance ratio while preserving chroma
  // direction. Clamp to [0, 255] to stay within sRGB.
  data[i]     = Math.min(255, Math.max(0, Math.round(r * ratio)));
  data[i + 1] = Math.min(255, Math.max(0, Math.round(g * ratio)));
  data[i + 2] = Math.min(255, Math.max(0, Math.round(b * ratio)));
}

console.log(`[gen-light-logo] writing ${OUT}`);
await img.write(OUT);
console.log('[gen-light-logo] done.');
