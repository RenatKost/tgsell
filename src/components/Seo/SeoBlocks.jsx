import { motion } from 'framer-motion';
import { NavLink } from 'react-router-dom';

export const Badge = ({ text }) => (
	<span className="inline-block bg-accent/10 border border-accent/20 text-accent text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">
		{text}
	</span>
);

export const PageShell = ({ badge, h1, lead, children }) => (
	<motion.div
		initial={{ opacity: 0, y: 20 }}
		animate={{ opacity: 1, y: 0 }}
		transition={{ duration: 0.4 }}
		className="py-12 max-w-4xl mx-auto"
	>
		<header className="mb-10">
			<Badge text={badge} />
			<h1 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white mb-3">{h1}</h1>
			<p className="text-base text-gray-500 dark:text-gray-400 leading-relaxed">{lead}</p>
		</header>
		{children}
	</motion.div>
);

export const Card = ({ children, className = '' }) => (
	<div className={'bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-6 lg:p-8 shadow-sm dark:shadow-neon mb-8 ' + className}>
		{children}
	</div>
);

export const Section = ({ title, children }) => (
	<section className="mb-8 last:mb-0">
		<h2 className="text-xl font-black text-gray-900 dark:text-white mb-3 flex items-center gap-2">
			<span className="w-1 h-5 rounded-full bg-accent flex-shrink-0" />
			{title}
		</h2>
		<div className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed space-y-2 pl-3">{children}</div>
	</section>
);

export const Steps = ({ items }) => (
	<ol className="space-y-3">
		{items.map((s, i) => (
			<li key={s.title} className="flex gap-3">
				<span className="w-7 h-7 rounded-lg bg-accent/10 text-accent font-black text-sm flex items-center justify-center flex-shrink-0">{i + 1}</span>
				<div>
					<p className="font-bold text-gray-900 dark:text-white">{s.title}</p>
					<p className="text-gray-500 dark:text-gray-400">{s.desc}</p>
				</div>
			</li>
		))}
	</ol>
);

export const Faq = ({ items }) => (
	<div className="space-y-3">
		{items.map((q) => (
			<details key={q.q} className="group rounded-xl border border-gray-100 dark:border-card-border p-4">
				<summary className="cursor-pointer font-bold text-gray-900 dark:text-white list-none flex justify-between gap-3">
					{q.q}
					<span className="text-accent group-open:rotate-45 transition-transform">+</span>
				</summary>
				<p className="mt-2 text-gray-500 dark:text-gray-400">{q.a}</p>
			</details>
		))}
	</div>
);

const primary = 'bg-accent text-black font-black px-8 py-3.5 rounded-xl shadow-lg shadow-accent/20 hover:brightness-110 transition-all text-sm uppercase tracking-wider';
const secondary = 'border border-gray-200 dark:border-card-border text-gray-800 dark:text-white font-bold px-8 py-3.5 rounded-xl hover:border-accent hover:text-accent transition-all text-sm uppercase tracking-wider';

export const Cta = ({ title, text, links }) => (
	<Card className="text-center">
		<h2 className="text-2xl font-black text-gray-900 dark:text-white mb-2">{title}</h2>
		{text && <p className="text-gray-500 dark:text-gray-400 mb-6">{text}</p>}
		<div className="flex gap-3 justify-center flex-wrap">
			{links.map((l, i) => (
				<NavLink key={l.to} to={l.to} className={i === 0 ? primary : secondary}>{l.label}</NavLink>
			))}
		</div>
	</Card>
);

export const A = ({ to, children }) => (
	<NavLink to={to} className="text-accent hover:underline">{children}</NavLink>
);
