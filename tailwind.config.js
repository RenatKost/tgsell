/** @type {import('tailwindcss').Config} */
export default {
	darkMode: 'class',
	content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
	theme: {
		extend: {
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
