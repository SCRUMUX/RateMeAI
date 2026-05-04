/**
 * useThemedLogo (1.36.0).
 *
 * Возвращает src логотипа, соответствующий активной теме.
 *  - dark theme  → ../assets/logo.png        (исходный, brand cyan glow на тёмной подложке)
 *  - light theme → ../assets/logo-light.png  (инвертированная luminance, cyan сохранён)
 *
 * logo-light.png генерируется build-time скриптом
 * web/scripts/generate-light-logo.mjs (luminance-only inversion с
 * сохранением hue) и коммитится в репозиторий. Re-run нужен только
 * при обновлении исходного logo.png.
 *
 * Vite импортирует оба ассета как отдельные hashed файлы. Браузер
 * грузит фактически отображаемый логотип по theme; второй
 * скачивается лениво (если пользователь когда-либо переключит тему),
 * после чего кешируется на CDN.
 */
import logoDarkSrc from '../assets/logo.png';
import logoLightSrc from '../assets/logo-light.png';
import { useTheme } from './theme';

export function useThemedLogo(): string {
  const { theme } = useTheme();
  return theme === 'light' ? logoLightSrc : logoDarkSrc;
}
