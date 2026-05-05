/**
 * FluidBackground (1.49.0).
 *
 * Interactive WebGL fluid layer для лендингов. Тонкий «след» от
 * курсора, быстро тает, мягкий velocity, цвета — наши primary через
 * --accent-r/g/b (category-aware). На idle — мягкие ambient splat'ы
 * раз в ~4с.
 *
 * 1.49.0:
 *  - Единый рендер на dark/light: ``mix-blend-mode: normal``,
 *    ``opacity: 0.7`` (см. .fluid-background в index.css). Убраны
 *    light-overrides конфигов, themeScale в pickSplatColor, двойная
 *    компиляция display-шейдера (SHADING/plain). Теперь нет «тёмных
 *    цветов» в светлой теме.
 *  - Мгновенная очистка dye-текстуры при смене ``data-category``,
 *    чтобы старый «хвост» не тащил предыдущий цвет.
 *
 * Порт Stam-style stable fluids на основе кода
 * Pavel DoGreat (https://github.com/PavelDoGreat/WebGL-Fluid-Simulation,
 * MIT). Адаптировано под TS, без BLOOM/SUNRAYS/CAPTURE (отключены
 * спекой), без random-цветов (наши primary), без auto-splat
 * (interactive_only), с reduced-motion guard, FPS-fallback и
 * battery-saver.
 */
import { useEffect, useRef } from 'react';

interface FluidConfig {
  SIM_RESOLUTION: number;
  DYE_RESOLUTION: number;
  DENSITY_DISSIPATION: number;
  VELOCITY_DISSIPATION: number;
  PRESSURE: number;
  PRESSURE_ITERATIONS: number;
  CURL: number;
  SPLAT_RADIUS: number;
  SPLAT_FORCE: number;
  SHADING: boolean;
}

interface RGB { r: number; g: number; b: number }

interface PointerState {
  id: number;
  texcoordX: number;
  texcoordY: number;
  prevTexcoordX: number;
  prevTexcoordY: number;
  deltaX: number;
  deltaY: number;
  down: boolean;
  moved: boolean;
  color: RGB;
}

interface FBO {
  texture: WebGLTexture;
  fbo: WebGLFramebuffer;
  width: number;
  height: number;
  texelSizeX: number;
  texelSizeY: number;
  attach(id: number): number;
}

interface DoubleFBO {
  width: number;
  height: number;
  texelSizeX: number;
  texelSizeY: number;
  read: FBO;
  write: FBO;
  swap(): void;
}

interface ExtCtx {
  gl: WebGLRenderingContext | WebGL2RenderingContext;
  isWebGL2: boolean;
  formatRGBA: { internalFormat: number; format: number } | null;
  formatRG: { internalFormat: number; format: number } | null;
  formatR: { internalFormat: number; format: number } | null;
  halfFloatTexType: number;
  supportLinearFiltering: boolean;
}

const VERT_SHADER = `
precision highp float;
attribute vec2 aPosition;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
uniform vec2 texelSize;
void main () {
  vUv = aPosition * 0.5 + 0.5;
  vL = vUv - vec2(texelSize.x, 0.0);
  vR = vUv + vec2(texelSize.x, 0.0);
  vT = vUv + vec2(0.0, texelSize.y);
  vB = vUv - vec2(0.0, texelSize.y);
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

const COPY_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
uniform sampler2D uTexture;
void main () { gl_FragColor = texture2D(uTexture, vUv); }`;

const CLEAR_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
uniform sampler2D uTexture;
uniform float value;
void main () { gl_FragColor = value * texture2D(uTexture, vUv); }`;

const SPLAT_SHADER = `
precision highp float;
precision highp sampler2D;
varying vec2 vUv;
uniform sampler2D uTarget;
uniform float aspectRatio;
uniform vec3 color;
uniform vec2 point;
uniform float radius;
void main () {
  vec2 p = vUv - point.xy;
  p.x *= aspectRatio;
  vec3 splat = exp(-dot(p, p) / radius) * color;
  vec3 base = texture2D(uTarget, vUv).xyz;
  gl_FragColor = vec4(base + splat, 1.0);
}`;

// Stam-style advection in a single MacCormack pass using manual filter.
// Manual bilinear used when extension OES_texture_half_float_linear missing.
const ADVECTION_SHADER = `
precision highp float;
precision highp sampler2D;
varying vec2 vUv;
uniform sampler2D uVelocity;
uniform sampler2D uSource;
uniform vec2 texelSize;
uniform vec2 dyeTexelSize;
uniform float dt;
uniform float dissipation;

vec4 bilerp (sampler2D sam, vec2 uv, vec2 tsize) {
  vec2 st = uv / tsize - 0.5;
  vec2 iuv = floor(st);
  vec2 fuv = fract(st);
  vec4 a = texture2D(sam, (iuv + vec2(0.5, 0.5)) * tsize);
  vec4 b = texture2D(sam, (iuv + vec2(1.5, 0.5)) * tsize);
  vec4 c = texture2D(sam, (iuv + vec2(0.5, 1.5)) * tsize);
  vec4 d = texture2D(sam, (iuv + vec2(1.5, 1.5)) * tsize);
  return mix(mix(a, b, fuv.x), mix(c, d, fuv.x), fuv.y);
}

void main () {
  #ifdef MANUAL_FILTERING
    vec2 coord = vUv - dt * bilerp(uVelocity, vUv, texelSize).xy * texelSize;
    vec4 result = bilerp(uSource, coord, dyeTexelSize);
  #else
    vec2 coord = vUv - dt * texture2D(uVelocity, vUv).xy * texelSize;
    vec4 result = texture2D(uSource, coord);
  #endif
  float decay = 1.0 + dissipation * dt;
  gl_FragColor = result / decay;
}`;

const DIVERGENCE_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
varying highp vec2 vL;
varying highp vec2 vR;
varying highp vec2 vT;
varying highp vec2 vB;
uniform sampler2D uVelocity;
void main () {
  float L = texture2D(uVelocity, vL).x;
  float R = texture2D(uVelocity, vR).x;
  float T = texture2D(uVelocity, vT).y;
  float B = texture2D(uVelocity, vB).y;
  vec2 C = texture2D(uVelocity, vUv).xy;
  if (vL.x < 0.0) { L = -C.x; }
  if (vR.x > 1.0) { R = -C.x; }
  if (vT.y > 1.0) { T = -C.y; }
  if (vB.y < 0.0) { B = -C.y; }
  float div = 0.5 * (R - L + T - B);
  gl_FragColor = vec4(div, 0.0, 0.0, 1.0);
}`;

const CURL_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
varying highp vec2 vL;
varying highp vec2 vR;
varying highp vec2 vT;
varying highp vec2 vB;
uniform sampler2D uVelocity;
void main () {
  float L = texture2D(uVelocity, vL).y;
  float R = texture2D(uVelocity, vR).y;
  float T = texture2D(uVelocity, vT).x;
  float B = texture2D(uVelocity, vB).x;
  float vorticity = R - L - T + B;
  gl_FragColor = vec4(0.5 * vorticity, 0.0, 0.0, 1.0);
}`;

const VORTICITY_SHADER = `
precision highp float;
precision highp sampler2D;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
uniform sampler2D uVelocity;
uniform sampler2D uCurl;
uniform float curl;
uniform float dt;
void main () {
  float L = texture2D(uCurl, vL).x;
  float R = texture2D(uCurl, vR).x;
  float T = texture2D(uCurl, vT).x;
  float B = texture2D(uCurl, vB).x;
  float C = texture2D(uCurl, vUv).x;
  vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L));
  force /= length(force) + 0.0001;
  force *= curl * C;
  force.y *= -1.0;
  vec2 velocity = texture2D(uVelocity, vUv).xy;
  velocity += force * dt;
  velocity = min(max(velocity, -1000.0), 1000.0);
  gl_FragColor = vec4(velocity, 0.0, 1.0);
}`;

const PRESSURE_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
varying highp vec2 vL;
varying highp vec2 vR;
varying highp vec2 vT;
varying highp vec2 vB;
uniform sampler2D uPressure;
uniform sampler2D uDivergence;
void main () {
  float L = texture2D(uPressure, vL).x;
  float R = texture2D(uPressure, vR).x;
  float T = texture2D(uPressure, vT).x;
  float B = texture2D(uPressure, vB).x;
  float C = texture2D(uPressure, vUv).x;
  float divergence = texture2D(uDivergence, vUv).x;
  float pressure = (L + R + B + T - divergence) * 0.25;
  gl_FragColor = vec4(pressure, 0.0, 0.0, 1.0);
}`;

const GRADIENT_SUBTRACT_SHADER = `
precision mediump float;
precision mediump sampler2D;
varying highp vec2 vUv;
varying highp vec2 vL;
varying highp vec2 vR;
varying highp vec2 vT;
varying highp vec2 vB;
uniform sampler2D uPressure;
uniform sampler2D uVelocity;
void main () {
  float L = texture2D(uPressure, vL).x;
  float R = texture2D(uPressure, vR).x;
  float T = texture2D(uPressure, vT).x;
  float B = texture2D(uPressure, vB).x;
  vec2 velocity = texture2D(uVelocity, vUv).xy;
  velocity.xy -= vec2(R - L, T - B);
  gl_FragColor = vec4(velocity, 0.0, 1.0);
}`;

const DISPLAY_SHADER_SOURCE = `
precision highp float;
precision highp sampler2D;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
uniform sampler2D uTexture;
uniform vec2 texelSize;

vec3 linearToGamma (vec3 color) {
  color = max(color, vec3(0));
  return max(1.055 * pow(color, vec3(0.416666667)) - 0.055, vec3(0));
}

void main () {
  vec3 c = texture2D(uTexture, vUv).rgb;
  #ifdef SHADING
    vec3 lc = texture2D(uTexture, vL).rgb;
    vec3 rc = texture2D(uTexture, vR).rgb;
    vec3 tc = texture2D(uTexture, vT).rgb;
    vec3 bc = texture2D(uTexture, vB).rgb;
    float dx = length(rc) - length(lc);
    float dy = length(tc) - length(bc);
    vec3 n = normalize(vec3(dx, dy, length(texelSize)));
    vec3 l = vec3(0.0, 0.0, 1.0);
    float diffuse = clamp(dot(n, l) + 0.7, 0.7, 1.0);
    c *= diffuse;
  #endif
  float a = max(c.r, max(c.g, c.b));
  gl_FragColor = vec4(c, a);
}`;

// 1.49.0: единый baseline для обеих тем. Убраны LIGHT_OVERRIDES —
// при mix-blend-mode: normal multiply-overhead на белом фоне больше
// не нужен (тёмных хвостов нет).
const DEFAULT_CONFIG: FluidConfig = {
  SIM_RESOLUTION: 96,
  DYE_RESOLUTION: 768,
  DENSITY_DISSIPATION: 4.5,
  VELOCITY_DISSIPATION: 2.5,
  PRESSURE: 0.8,
  PRESSURE_ITERATIONS: 12,
  CURL: 6,
  SPLAT_RADIUS: 0.18,
  SPLAT_FORCE: 1500,
  SHADING: false,
};

function getWebGLContext(canvas: HTMLCanvasElement): ExtCtx | null {
  const params: WebGLContextAttributes = {
    alpha: true,
    depth: false,
    stencil: false,
    antialias: false,
    preserveDrawingBuffer: false,
    premultipliedAlpha: false,
  };

  let gl: WebGLRenderingContext | WebGL2RenderingContext | null =
    canvas.getContext('webgl2', params) as WebGL2RenderingContext | null;
  const isWebGL2 = !!gl;
  if (!gl) {
    gl = (canvas.getContext('webgl', params) ||
      canvas.getContext('experimental-webgl', params)) as WebGLRenderingContext | null;
  }
  if (!gl) return null;

  let halfFloat: { HALF_FLOAT_OES: number } | null = null;
  let supportLinearFiltering = false;

  if (isWebGL2) {
    (gl as WebGL2RenderingContext).getExtension('EXT_color_buffer_float');
    supportLinearFiltering = !!(gl as WebGL2RenderingContext).getExtension('OES_texture_float_linear');
  } else {
    halfFloat = (gl as WebGLRenderingContext).getExtension('OES_texture_half_float') as { HALF_FLOAT_OES: number } | null;
    supportLinearFiltering = !!(gl as WebGLRenderingContext).getExtension('OES_texture_half_float_linear');
  }

  gl.clearColor(0.0, 0.0, 0.0, 1.0);

  const halfFloatTexType = isWebGL2
    ? (gl as WebGL2RenderingContext).HALF_FLOAT
    : halfFloat?.HALF_FLOAT_OES ?? gl.UNSIGNED_BYTE;

  let formatRGBA, formatRG, formatR;
  if (isWebGL2) {
    const gl2 = gl as WebGL2RenderingContext;
    formatRGBA = getSupportedFormat(gl2, gl2.RGBA16F, gl2.RGBA, halfFloatTexType);
    formatRG = getSupportedFormat(gl2, gl2.RG16F, gl2.RG, halfFloatTexType);
    formatR = getSupportedFormat(gl2, gl2.R16F, gl2.RED, halfFloatTexType);
  } else {
    formatRGBA = getSupportedFormat(gl, gl.RGBA, gl.RGBA, halfFloatTexType);
    formatRG = getSupportedFormat(gl, gl.RGBA, gl.RGBA, halfFloatTexType);
    formatR = getSupportedFormat(gl, gl.RGBA, gl.RGBA, halfFloatTexType);
  }

  return { gl, isWebGL2, formatRGBA, formatRG, formatR, halfFloatTexType, supportLinearFiltering };
}

function getSupportedFormat(
  gl: WebGLRenderingContext | WebGL2RenderingContext,
  internalFormat: number,
  format: number,
  type: number,
): { internalFormat: number; format: number } | null {
  if (!supportRenderTextureFormat(gl, internalFormat, format, type)) {
    if ('R16F' in gl && internalFormat === (gl as WebGL2RenderingContext).R16F) {
      return getSupportedFormat(gl, (gl as WebGL2RenderingContext).RG16F, (gl as WebGL2RenderingContext).RG, type);
    }
    if ('RG16F' in gl && internalFormat === (gl as WebGL2RenderingContext).RG16F) {
      return getSupportedFormat(gl, (gl as WebGL2RenderingContext).RGBA16F, (gl as WebGL2RenderingContext).RGBA, type);
    }
    return null;
  }
  return { internalFormat, format };
}

function supportRenderTextureFormat(
  gl: WebGLRenderingContext | WebGL2RenderingContext,
  internalFormat: number,
  format: number,
  type: number,
): boolean {
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, 4, 4, 0, format, type, null);

  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  return status === gl.FRAMEBUFFER_COMPLETE;
}

function compileShader(
  gl: WebGLRenderingContext | WebGL2RenderingContext,
  type: number,
  source: string,
  keywords?: string[],
): WebGLShader | null {
  const finalSource = addKeywords(source, keywords);
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, finalSource);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn('[FluidBackground] shader compile error:', gl.getShaderInfoLog(shader));
    return null;
  }
  return shader;
}

function addKeywords(source: string, keywords?: string[]): string {
  if (!keywords || keywords.length === 0) return source;
  let prefix = '';
  for (const k of keywords) prefix += `#define ${k}\n`;
  return prefix + source;
}

function createProgram(
  gl: WebGLRenderingContext | WebGL2RenderingContext,
  vert: WebGLShader,
  frag: WebGLShader,
): { program: WebGLProgram; uniforms: Record<string, WebGLUniformLocation> } | null {
  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vert);
  gl.attachShader(program, frag);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.warn('[FluidBackground] program link error:', gl.getProgramInfoLog(program));
    return null;
  }
  const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
  const uniforms: Record<string, WebGLUniformLocation> = {};
  for (let i = 0; i < count; i++) {
    const info = gl.getActiveUniform(program, i);
    if (!info) continue;
    const loc = gl.getUniformLocation(program, info.name);
    if (loc) uniforms[info.name] = loc;
  }
  return { program, uniforms };
}

// 1.42.0: theme/category-aware кэш. Только primary — secondary
// убран, чтобы splat-color **всегда совпадал** с активной
// категорией (cyan/purple/pink/orange). Раньше mix(primary,
// secondary, t=random) уводил оттенок в дополняющий цвет
// (например social: cyan→violet) — пользователь воспринимал это
// как «не тот цвет».
const themeCache: {
  primary: RGB;
  isLight: boolean;
  category: string;
} = {
  primary: { r: 0, g: 0.94, b: 1.0 },
  isLight: false,
  category: '',
};

function parseAccent(root: CSSStyleDeclaration, prefix: string, fallback: RGB): RGB {
  const r = +(root.getPropertyValue(`${prefix}-r`).trim() || fallback.r * 255) / 255;
  const g = +(root.getPropertyValue(`${prefix}-g`).trim() || fallback.g * 255) / 255;
  const b = +(root.getPropertyValue(`${prefix}-b`).trim() || fallback.b * 255) / 255;
  return { r, g, b };
}

interface ThemeRefreshResult {
  themeChanged: boolean;
  categoryChanged: boolean;
}

function refreshThemeCache(): ThemeRefreshResult {
  if (typeof document === 'undefined') {
    return { themeChanged: false, categoryChanged: false };
  }
  // Active accent живёт на элементе с data-category (root <div> в Landing/AppPage).
  // Если он есть — берём computed style оттуда, иначе fallback на <html>.
  const sourceEl =
    (document.querySelector('[data-category]') as HTMLElement | null) ??
    document.documentElement;
  const root = getComputedStyle(sourceEl);
  const primary = parseAccent(root, '--accent', { r: 0, g: 0.94, b: 1.0 });
  const isLight = document.documentElement.dataset.theme === 'light';
  const category = (sourceEl as HTMLElement).dataset?.category ?? '';
  const themeChanged = isLight !== themeCache.isLight;
  const categoryChanged = category !== themeCache.category;
  themeCache.primary = primary;
  themeCache.isLight = isLight;
  themeCache.category = category;
  return { themeChanged, categoryChanged };
}

/**
 * 1.49.0: Single-hue splat color. Каждый splat = primary категории
 * с ±12% jitter по каналам (даёт мягкий разброс яркости в пределах
 * того же оттенка, без ухода в дополняющий цвет).
 *
 * Поведение единое для dark/light: ``speedScale = min(1,
 * speed*12)`` — мягкое приглушение цвета на медленных движениях.
 * Так как canvas рисуется через ``mix-blend-mode: normal;
 * opacity: 0.7`` (см. .fluid-background в index.css), на белой
 * подложке полупрозрачный full-saturation cyan = светло-cyan tint,
 * никаких тёмных пятен.
 */
function pickSplatColor(speed: number): RGB {
  const a = themeCache.primary;
  const jR = 0.88 + Math.random() * 0.24;
  const jG = 0.88 + Math.random() * 0.24;
  const jB = 0.88 + Math.random() * 0.24;
  const speedScale = Math.min(1, speed * 12);
  return {
    r: a.r * jR * speedScale,
    g: a.g * jG * speedScale,
    b: a.b * jB * speedScale,
  };
}

function prefersReducedMotion(): boolean {
  if (typeof matchMedia === 'undefined') return false;
  return matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function isMobile(): boolean {
  if (typeof window === 'undefined') return false;
  return window.innerWidth < 768;
}

export default function FluidBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = getWebGLContext(canvas);
    if (!ctx || !ctx.formatRGBA || !ctx.formatRG || !ctx.formatR) return;

    const { gl } = ctx;

    const config: FluidConfig = {
      ...DEFAULT_CONFIG,
      SIM_RESOLUTION: isMobile() ? 48 : DEFAULT_CONFIG.SIM_RESOLUTION,
      DYE_RESOLUTION: isMobile() ? 384 : DEFAULT_CONFIG.DYE_RESOLUTION,
    };

    refreshThemeCache();

    const blitVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, blitVbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, -1, 1, 1, 1, 1, -1]), gl.STATIC_DRAW);
    const blitIbo = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, blitIbo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0, 1, 2, 0, 2, 3]), gl.STATIC_DRAW);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.enableVertexAttribArray(0);

    function blit(target: FBO | null, clear = false) {
      if (target) {
        gl.viewport(0, 0, target.width, target.height);
        gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo);
      } else {
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      }
      if (clear) {
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
      }
      gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0);
    }

    const vertShader = compileShader(gl, gl.VERTEX_SHADER, VERT_SHADER);
    if (!vertShader) return;

    const advectionKeywords = ctx.supportLinearFiltering ? undefined : ['MANUAL_FILTERING'];
    const fragCopy = compileShader(gl, gl.FRAGMENT_SHADER, COPY_SHADER);
    const fragClear = compileShader(gl, gl.FRAGMENT_SHADER, CLEAR_SHADER);
    const fragSplat = compileShader(gl, gl.FRAGMENT_SHADER, SPLAT_SHADER);
    const fragAdvection = compileShader(gl, gl.FRAGMENT_SHADER, ADVECTION_SHADER, advectionKeywords);
    const fragDivergence = compileShader(gl, gl.FRAGMENT_SHADER, DIVERGENCE_SHADER);
    const fragCurl = compileShader(gl, gl.FRAGMENT_SHADER, CURL_SHADER);
    const fragVorticity = compileShader(gl, gl.FRAGMENT_SHADER, VORTICITY_SHADER);
    const fragPressure = compileShader(gl, gl.FRAGMENT_SHADER, PRESSURE_SHADER);
    const fragGradSub = compileShader(gl, gl.FRAGMENT_SHADER, GRADIENT_SUBTRACT_SHADER);
    // 1.49.0: один display-шейдер без SHADING для обеих тем. Раньше
    // компилировались два варианта (SHADING для dark, plain для
    // light), но diffuse-кромки на белом давали тёмные «оттенки»,
    // которые пользователь воспринимал как «другой эффект».
    const fragDisplay = compileShader(gl, gl.FRAGMENT_SHADER, DISPLAY_SHADER_SOURCE, []);

    if (
      !fragCopy || !fragClear || !fragSplat || !fragAdvection || !fragDivergence ||
      !fragCurl || !fragVorticity || !fragPressure || !fragGradSub ||
      !fragDisplay
    ) return;

    const copyProg = createProgram(gl, vertShader, fragCopy);
    const clearProg = createProgram(gl, vertShader, fragClear);
    const splatProg = createProgram(gl, vertShader, fragSplat);
    const advectionProg = createProgram(gl, vertShader, fragAdvection);
    const divergenceProg = createProgram(gl, vertShader, fragDivergence);
    const curlProg = createProgram(gl, vertShader, fragCurl);
    const vorticityProg = createProgram(gl, vertShader, fragVorticity);
    const pressureProg = createProgram(gl, vertShader, fragPressure);
    const gradSubProg = createProgram(gl, vertShader, fragGradSub);
    const displayProg = createProgram(gl, vertShader, fragDisplay);

    if (
      !copyProg || !clearProg || !splatProg || !advectionProg || !divergenceProg ||
      !curlProg || !vorticityProg || !pressureProg || !gradSubProg ||
      !displayProg
    ) return;

    function createFBO(w: number, h: number, internalFormat: number, format: number, type: number, param: number): FBO {
      gl.activeTexture(gl.TEXTURE0);
      const texture = gl.createTexture()!;
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, param);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, param);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, w, h, 0, format, type, null);

      const fbo = gl.createFramebuffer()!;
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
      gl.viewport(0, 0, w, h);
      gl.clear(gl.COLOR_BUFFER_BIT);

      const texelSizeX = 1.0 / w;
      const texelSizeY = 1.0 / h;
      return {
        texture,
        fbo,
        width: w,
        height: h,
        texelSizeX,
        texelSizeY,
        attach(id: number) {
          gl.activeTexture(gl.TEXTURE0 + id);
          gl.bindTexture(gl.TEXTURE_2D, texture);
          return id;
        },
      };
    }

    function createDoubleFBO(w: number, h: number, internalFormat: number, format: number, type: number, param: number): DoubleFBO {
      let read = createFBO(w, h, internalFormat, format, type, param);
      let write = createFBO(w, h, internalFormat, format, type, param);
      return {
        width: w,
        height: h,
        texelSizeX: 1.0 / w,
        texelSizeY: 1.0 / h,
        get read() { return read; },
        set read(v) { read = v; },
        get write() { return write; },
        set write(v) { write = v; },
        swap() { const tmp = read; read = write; write = tmp; },
      };
    }

    function getResolution(res: number): { width: number; height: number } {
      const aspect = gl.drawingBufferWidth / gl.drawingBufferHeight;
      const min = Math.round(res);
      const max = Math.round(res * (aspect >= 1 ? aspect : 1 / aspect));
      return aspect >= 1 ? { width: max, height: min } : { width: min, height: max };
    }

    let dye: DoubleFBO;
    let velocity: DoubleFBO;
    let divergence: FBO;
    let curl: FBO;
    let pressure: DoubleFBO;

    function initFBOs() {
      const simRes = getResolution(config.SIM_RESOLUTION);
      const dyeRes = getResolution(config.DYE_RESOLUTION);
      const texType = ctx!.halfFloatTexType;
      const rgba = ctx!.formatRGBA!;
      const rg = ctx!.formatRG!;
      const r = ctx!.formatR!;
      const filtering = ctx!.supportLinearFiltering ? gl.LINEAR : gl.NEAREST;

      gl.disable(gl.BLEND);
      dye = createDoubleFBO(dyeRes.width, dyeRes.height, rgba.internalFormat, rgba.format, texType, filtering);
      velocity = createDoubleFBO(simRes.width, simRes.height, rg.internalFormat, rg.format, texType, filtering);
      divergence = createFBO(simRes.width, simRes.height, r.internalFormat, r.format, texType, gl.NEAREST);
      curl = createFBO(simRes.width, simRes.height, r.internalFormat, r.format, texType, gl.NEAREST);
      pressure = createDoubleFBO(simRes.width, simRes.height, r.internalFormat, r.format, texType, gl.NEAREST);
    }

    function resizeCanvas() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.floor(window.innerWidth * dpr);
      const h = Math.floor(window.innerHeight * dpr);
      if (canvas!.width !== w || canvas!.height !== h) {
        canvas!.width = w;
        canvas!.height = h;
        canvas!.style.width = `${window.innerWidth}px`;
        canvas!.style.height = `${window.innerHeight}px`;
        return true;
      }
      return false;
    }

    resizeCanvas();
    initFBOs();

    function splat(x: number, y: number, dx: number, dy: number, color: RGB) {
      const radius = config.SPLAT_RADIUS;
      gl.useProgram(splatProg!.program);
      gl.uniform1i(splatProg!.uniforms['uTarget'], velocity.read.attach(0));
      gl.uniform1f(splatProg!.uniforms['aspectRatio'], canvas!.width / canvas!.height);
      gl.uniform2f(splatProg!.uniforms['point'], x, y);
      gl.uniform3f(splatProg!.uniforms['color'], dx, dy, 0);
      gl.uniform1f(splatProg!.uniforms['radius'], correctRadius(radius / 100));
      blit(velocity.write);
      velocity.swap();

      gl.useProgram(splatProg!.program);
      gl.uniform1i(splatProg!.uniforms['uTarget'], dye.read.attach(0));
      gl.uniform3f(splatProg!.uniforms['color'], color.r, color.g, color.b);
      blit(dye.write);
      dye.swap();
    }

    function correctRadius(radius: number): number {
      const aspect = canvas!.width / canvas!.height;
      if (aspect > 1) return radius * aspect;
      return radius;
    }

    function splatPointer(p: PointerState, speed: number) {
      const force = config.SPLAT_FORCE;
      const dx = p.deltaX * force;
      const dy = p.deltaY * force;
      // 1.49.0: цвет рассчитывается на момент splat'а с учётом speed —
      // бледнее на медленных движениях. Единая формула для обеих тем
      // (см. pickSplatColor).
      const color = pickSplatColor(speed);
      splat(p.texcoordX, p.texcoordY, dx, dy, color);
    }

    const pointers: PointerState[] = [{
      id: -1,
      texcoordX: 0,
      texcoordY: 0,
      prevTexcoordX: 0,
      prevTexcoordY: 0,
      deltaX: 0,
      deltaY: 0,
      down: false,
      moved: false,
      color: pickSplatColor(0),
    }];

    function correctDeltaX(d: number): number {
      const aspect = canvas!.width / canvas!.height;
      if (aspect < 1) return d * aspect;
      return d;
    }
    function correctDeltaY(d: number): number {
      const aspect = canvas!.width / canvas!.height;
      if (aspect > 1) return d / aspect;
      return d;
    }

    function updatePointerMoveData(p: PointerState, posX: number, posY: number) {
      p.prevTexcoordX = p.texcoordX;
      p.prevTexcoordY = p.texcoordY;
      p.texcoordX = posX / canvas!.width;
      p.texcoordY = 1.0 - posY / canvas!.height;
      p.deltaX = correctDeltaX(p.texcoordX - p.prevTexcoordX);
      p.deltaY = correctDeltaY(p.texcoordY - p.prevTexcoordY);
      p.moved = Math.abs(p.deltaX) > 0 || Math.abs(p.deltaY) > 0;
    }

    function updatePointerDownData(p: PointerState, posX: number, posY: number) {
      p.down = true;
      p.moved = false;
      p.texcoordX = posX / canvas!.width;
      p.texcoordY = 1.0 - posY / canvas!.height;
      p.prevTexcoordX = p.texcoordX;
      p.prevTexcoordY = p.texcoordY;
      p.deltaX = 0;
      p.deltaY = 0;
      // p.color заполняем при splat'е (см. splatPointer); здесь
      // ставим placeholder чтобы не нарушать тип.
      p.color = pickSplatColor(0);
    }

    // Threshold по квадрату delta'ы (нормализованной к viewport):
    // ниже этого порога медленный курсор не оставляет splat-а вовсе
    // (problem 3 в plan'е). Значение подобрано так, чтобы обычное
    // прокручивание мышью с типичной скоростью давало уверенный splat,
    // а «дрейф» курсора за чтением — нет.
    const SPLAT_SPEED_THRESHOLD_SQ = 0.0001;

    function applyInputs(): boolean {
      let didSplat = false;
      for (const p of pointers) {
        if (!p.moved) continue;
        p.moved = false;
        const speedSq = p.deltaX * p.deltaX + p.deltaY * p.deltaY;
        if (speedSq < SPLAT_SPEED_THRESHOLD_SQ) continue;
        splatPointer(p, Math.sqrt(speedSq));
        didSplat = true;
      }
      return didSplat;
    }

    // 1.43.0: pointer-handlers больше не управляют RAF (raf всегда
    // running, ambient idle-splats держат «жизнь» фона). Hidden-tab
    // pause обеспечивается самим браузером — он не вызывает RAF
    // когда вкладка не visible.
    function onPointerMove(e: PointerEvent) {
      const p = pointers[0];
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      updatePointerMoveData(p, e.clientX * dpr, e.clientY * dpr);
    }
    function onPointerDown(e: PointerEvent) {
      const p = pointers[0];
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      updatePointerDownData(p, e.clientX * dpr, e.clientY * dpr);
    }
    function onTouchMove(e: TouchEvent) {
      const t = e.touches[0];
      if (!t) return;
      const p = pointers[0];
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      updatePointerMoveData(p, t.clientX * dpr, t.clientY * dpr);
    }
    function onTouchStart(e: TouchEvent) {
      const t = e.touches[0];
      if (!t) return;
      const p = pointers[0];
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      updatePointerDownData(p, t.clientX * dpr, t.clientY * dpr);
    }

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('pointerdown', onPointerDown, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('touchstart', onTouchStart, { passive: true });

    function step(dt: number) {
      gl.disable(gl.BLEND);

      // Curl
      gl.useProgram(curlProg!.program);
      gl.uniform2f(curlProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      gl.uniform1i(curlProg!.uniforms['uVelocity'], velocity.read.attach(0));
      blit(curl);

      // Vorticity
      gl.useProgram(vorticityProg!.program);
      gl.uniform2f(vorticityProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      gl.uniform1i(vorticityProg!.uniforms['uVelocity'], velocity.read.attach(0));
      gl.uniform1i(vorticityProg!.uniforms['uCurl'], curl.attach(1));
      gl.uniform1f(vorticityProg!.uniforms['curl'], config.CURL);
      gl.uniform1f(vorticityProg!.uniforms['dt'], dt);
      blit(velocity.write);
      velocity.swap();

      // Divergence
      gl.useProgram(divergenceProg!.program);
      gl.uniform2f(divergenceProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      gl.uniform1i(divergenceProg!.uniforms['uVelocity'], velocity.read.attach(0));
      blit(divergence);

      // Decay pressure
      gl.useProgram(clearProg!.program);
      gl.uniform1i(clearProg!.uniforms['uTexture'], pressure.read.attach(0));
      gl.uniform1f(clearProg!.uniforms['value'], config.PRESSURE);
      blit(pressure.write);
      pressure.swap();

      // Pressure iter
      gl.useProgram(pressureProg!.program);
      gl.uniform2f(pressureProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      gl.uniform1i(pressureProg!.uniforms['uDivergence'], divergence.attach(0));
      for (let i = 0; i < config.PRESSURE_ITERATIONS; i++) {
        gl.uniform1i(pressureProg!.uniforms['uPressure'], pressure.read.attach(1));
        blit(pressure.write);
        pressure.swap();
      }

      // Gradient subtract
      gl.useProgram(gradSubProg!.program);
      gl.uniform2f(gradSubProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      gl.uniform1i(gradSubProg!.uniforms['uPressure'], pressure.read.attach(0));
      gl.uniform1i(gradSubProg!.uniforms['uVelocity'], velocity.read.attach(1));
      blit(velocity.write);
      velocity.swap();

      // Advect velocity
      gl.useProgram(advectionProg!.program);
      gl.uniform2f(advectionProg!.uniforms['texelSize'], velocity.texelSizeX, velocity.texelSizeY);
      if (!ctx!.supportLinearFiltering) {
        gl.uniform2f(advectionProg!.uniforms['dyeTexelSize'], velocity.texelSizeX, velocity.texelSizeY);
      }
      const velId = velocity.read.attach(0);
      gl.uniform1i(advectionProg!.uniforms['uVelocity'], velId);
      gl.uniform1i(advectionProg!.uniforms['uSource'], velId);
      gl.uniform1f(advectionProg!.uniforms['dt'], dt);
      gl.uniform1f(advectionProg!.uniforms['dissipation'], config.VELOCITY_DISSIPATION);
      blit(velocity.write);
      velocity.swap();

      // Advect dye
      gl.useProgram(advectionProg!.program);
      if (!ctx!.supportLinearFiltering) {
        gl.uniform2f(advectionProg!.uniforms['dyeTexelSize'], dye.texelSizeX, dye.texelSizeY);
      }
      gl.uniform1i(advectionProg!.uniforms['uVelocity'], velocity.read.attach(0));
      gl.uniform1i(advectionProg!.uniforms['uSource'], dye.read.attach(1));
      gl.uniform1f(advectionProg!.uniforms['dissipation'], config.DENSITY_DISSIPATION);
      blit(dye.write);
      dye.swap();
    }

    function render() {
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.useProgram(displayProg!.program);
      gl.uniform2f(displayProg!.uniforms['texelSize'], 1.0 / gl.drawingBufferWidth, 1.0 / gl.drawingBufferHeight);
      gl.uniform1i(displayProg!.uniforms['uTexture'], dye.read.attach(0));
      blit(null);
    }

    /**
     * 1.49.0: Полная очистка dye-текстуры (read + write FBO).
     * Вызывается из observer'а при смене ``data-category`` —
     * мгновенно убирает «хвост» предыдущего цвета. Без этого хвост
     * продолжал тлеть ~600ms после смены категории, и пользователь
     * видел старый оттенок одновременно с новым.
     */
    function clearDye() {
      gl.bindFramebuffer(gl.FRAMEBUFFER, dye.read.fbo);
      gl.viewport(0, 0, dye.width, dye.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.bindFramebuffer(gl.FRAMEBUFFER, dye.write.fbo);
      gl.viewport(0, 0, dye.width, dye.height);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    }

    let lastTime = performance.now();
    const fpsWindow: number[] = [];
    let degradeChecked = false;
    let raf = 0;
    // 1.43.0: Ambient idle splats заменили RAF-pause из 1.40.0.
    // Раньше RAF останавливался через 2s бездействия → на длинных
    // wizard-шагах (ожидание анализа) фон визуально «исчезал».
    // Теперь раз в AMBIENT_INTERVAL_MS делаем мягкий случайный
    // splat в случайной точке viewport'а — фон всегда «дышит».
    // На скрытой вкладке браузер сам не вызывает RAF, energy не
    // тратится.
    const AMBIENT_INTERVAL_MS = 4000;
    let lastAmbientAt = performance.now();

    function ambientSplat() {
      // Случайная точка в центральной 70%-зоне — не у самых краёв,
      // чтобы splat выглядел естественно (не «вырывался» в углу).
      const x = 0.15 + Math.random() * 0.7;
      const y = 0.15 + Math.random() * 0.7;
      // Случайное направление + умеренная сила (40% от user-splat'а).
      const angle = Math.random() * Math.PI * 2;
      const ambientSpeed = 0.05;
      const dx = Math.cos(angle) * ambientSpeed * config.SPLAT_FORCE;
      const dy = Math.sin(angle) * ambientSpeed * config.SPLAT_FORCE;
      const color = pickSplatColor(ambientSpeed);
      splat(x, y, dx, dy, color);
    }

    // Resize обрабатываем deferred — синхронный initFBOs() в обработчике
    // resize блокирует frame на ~10 ms на больших экранах.
    let pendingResize = false;
    function onResize() { pendingResize = true; }
    window.addEventListener('resize', onResize, { passive: true });

    function frame() {
      const now = performance.now();
      const dt = Math.min((now - lastTime) / 1000, 0.016666);
      lastTime = now;

      if (pendingResize) {
        if (resizeCanvas()) initFBOs();
        pendingResize = false;
      }

      const fps = dt > 0 ? 1 / dt : 60;
      fpsWindow.push(fps);
      if (fpsWindow.length > 60) fpsWindow.shift();
      if (!degradeChecked && fpsWindow.length >= 60) {
        const avg = fpsWindow.reduce((a, b) => a + b, 0) / fpsWindow.length;
        if (avg < 45 && config.DYE_RESOLUTION > 256) {
          config.DYE_RESOLUTION = Math.max(256, Math.floor(config.DYE_RESOLUTION / 2));
          initFBOs();
        }
        degradeChecked = true;
      }

      applyInputs();
      if (now - lastAmbientAt > AMBIENT_INTERVAL_MS) {
        ambientSplat();
        lastAmbientAt = now;
      }
      step(dt);
      render();

      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    // 1.49.0: refreshThemeCache в rAF + мгновенный clear dye при
    // смене data-category. Без rAF-обёртки getComputedStyle после
    // mutation возвращает старые CSS-переменные (style commit ещё
    // не произошёл). При смене категории очищаем dye-текстуру
    // полностью — иначе старый «хвост» в предыдущем цвете тлеет
    // ~600ms и пользователь видит «запоздание на один шаг».
    const themeObserver = new MutationObserver(() => {
      requestAnimationFrame(() => {
        const { categoryChanged } = refreshThemeCache();
        if (categoryChanged) clearDye();
      });
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    document.querySelectorAll('[data-category]').forEach((el) => {
      themeObserver.observe(el, {
        attributes: true,
        attributeFilter: ['data-category'],
      });
    });

    let cancelled = false;
    // Battery saver — non-blocking, returns null on iOS Safari.
    type NavigatorWithBattery = Navigator & { getBattery?: () => Promise<{ level: number; charging: boolean }> };
    const nav = navigator as NavigatorWithBattery;
    nav.getBattery?.()
      .then((battery) => {
        if (cancelled) return;
        if (battery.level < 0.2 && !battery.charging) {
          cancelAnimationFrame(raf);
          raf = 0;
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (raf) cancelAnimationFrame(raf);
      themeObserver.disconnect();
      window.removeEventListener('resize', onResize);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchstart', onTouchStart);
    };
  }, []);

  if (prefersReducedMotion()) return null;

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="fluid-background"
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        // 1.40.0: понижено до 0 (было 1). Все wizard/landing sections,
        // NavBar и модалки гарантированно над фоном благодаря
        // ``isolation: isolate`` (см. index.css guard).
        zIndex: 0,
      }}
    />
  );
}
