/** @type {import('tailwindcss').Config} */
export default {
	darkMode: 'class',
	content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
	theme: {
		extend: {
			colors: {
				page: '#080E0E',
				card: '#0D1717',
				'card-border': '#1A3A2A',
				'card-inner': '#0A1414',
				'card-hover': '#122222',
				accent: '#00FF88',
			},
			boxShadow: {
				neon: '0 0 15px rgba(0, 255, 136, 0.08)',
				'neon-lg': '0 0 30px rgba(0, 255, 136, 0.12)',
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
