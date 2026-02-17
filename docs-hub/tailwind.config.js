/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            color: '#e5e7eb',
            maxWidth: 'none',
            h1: {
              color: '#ffffff',
            },
            h2: {
              color: '#ffffff',
            },
            h3: {
              color: '#f3f4f6',
            },
            code: {
              color: '#fbbf24',
              backgroundColor: '#1f2937',
            },
            'code::before': {
              content: '""',
            },
            'code::after': {
              content: '""',
            },
            pre: {
              backgroundColor: '#111827',
              border: '1px solid #374151',
            },
            'pre code': {
              backgroundColor: 'transparent',
              color: '#e5e7eb',
            },
            table: {
              backgroundColor: '#1f2937',
            },
            thead: {
              backgroundColor: '#374151',
            },
            'thead th': {
              color: '#ffffff',
              borderBottomColor: '#4b5563',
            },
            'tbody td': {
              borderBottomColor: '#374151',
              color: '#d1d5db',
            },
            blockquote: {
              color: '#9ca3af',
              borderLeftColor: '#60a5fa',
            },
            strong: {
              color: '#ffffff',
            },
            a: {
              color: '#60a5fa',
              '&:hover': {
                color: '#93c5fd',
              },
            },
            li: {
              color: '#d1d5db',
            },
            p: {
              color: '#d1d5db',
            },
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}