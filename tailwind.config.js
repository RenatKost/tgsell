/** @type {import('tailwindcss').Config} */
export default {
	darkMode: 'class',
	content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
	theme: {
		extend: {
			colors: {
				page: '#0F1923',
				card: '#1A2332',
				'card-border': '#243447',
				'card-inner': '#152238',
				'card-hover': '#1F2D42',
				accent: '#22C55E',
			},
			keyframes: {
				fadeIn: {
					'0%': { opacity: '0', transform: 'scale(0.95) translateY(10px)' },
					'100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
				},
			},
			animation: {
				fadeIn: 'fadeIn 0.2s ease-out',
			},
		},
	},
	plugins: [],
};
