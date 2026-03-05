// @ts-check
import { defineConfig } from 'astro/config';
import { resolve } from 'path';

const isProd = process.env.NODE_ENV === 'production';

// https://astro.build/config
export default defineConfig({
  site: 'https://generalusermodels.github.io',
  base: isProd ? '/nap/' : '/',
  vite: {
    publicDir: resolve(import.meta.dirname, 'public'),
  },
});
