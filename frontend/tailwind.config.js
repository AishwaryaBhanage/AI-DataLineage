/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      colors: {
        // Brand palette — interpolated from the green → teal gradient:
        //   start: #5ba479 (sage green)
        //   end:   #2f6379 (muted teal-blue)
        // Used for accents, icons, focus rings, active states.
        // For visual flair (buttons, logo, hero) use `.bg-gradient-brand`.
        brand: {
          50:  '#ecf5f1',  // very light mix
          100: '#d4eadf',
          200: '#a8d5c2',
          300: '#7dbfa4',
          400: '#5ba479',  // gradient start
          500: '#498b7b',
          600: '#2f6379',  // gradient end — primary solid
          700: '#264f60',
          800: '#1c3a48',
          900: '#122530',
        },
      },
      backgroundImage: {
        'gradient-brand':
          'linear-gradient(135deg, #5ba479 0%, #498b7b 50%, #2f6379 100%)',
        'gradient-brand-soft':
          'linear-gradient(135deg, #ecf5f1 0%, #d4eadf 100%)',
        'gradient-brand-vertical':
          'linear-gradient(180deg, #5ba479 0%, #2f6379 100%)',
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)',
        pop: '0 10px 30px -5px rgb(0 0 0 / 0.08), 0 4px 10px -4px rgb(0 0 0 / 0.05)',
        brand: '0 4px 14px 0 rgba(47, 99, 121, 0.25)',
      },
    },
  },
  plugins: [],
}
