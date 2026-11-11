import { NavLink } from 'react-router-dom';
import { useBlogHead, useBlogIndex, formatBlogDate } from '../hooks/useBlogData';
import './escrow.css';
import './premium.css';
import './public.css';
import './blog.css';

const TITLE = 'Блог TgSell — купівля, продаж і перевірка Telegram-каналів';
const DESCRIPTION = 'Практичні статті про купівлю, продаж, оцінку та перевірку Telegram-каналів і про безпечні угоди через гарант TgSell.';

const BlogPage = () => {
	const { status, articles } = useBlogIndex();
	useBlogHead({ path: '/blog', title: TITLE, description: DESCRIPTION });

	return (
		<div className="esc-page prm-pub blog-page relative pt-24 md:pt-32 pb-12 max-w-4xl mx-auto px-4">
			<div className="esc-bg esc-bg-short" aria-hidden="true"><span className="esc-grid" /><span className="esc-blob esc-blob-1" /><span className="esc-blob esc-blob-2" /></div>
			<header className="mb-10">
				<span className="inline-block bg-accent/10 border border-accent/20 text-accent text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">Блог</span>
				<h1 className="esc-title text-3xl sm:text-4xl font-black text-gray-900 dark:text-white mb-2">Блог TgSell</h1>
				<p className="text-sm text-gray-500 dark:text-gray-400">Практичні поради про купівлю, продаж, оцінку та перевірку Telegram-каналів.</p>
			</header>

			{status === 'loading' && <p className="text-sm text-gray-400" role="status">Завантаження…</p>}
			{status === 'error' && <p className="text-sm text-gray-500 dark:text-gray-400" role="alert">Не вдалося завантажити статті. Спробуйте оновити сторінку.</p>}
			{status === 'ok' && articles.length === 0 && (
				<p className="text-sm text-gray-500 dark:text-gray-400">Статті незабаром з’являться.</p>
			)}
			{status === 'ok' && articles.length > 0 && (
				<ul className="grid gap-4 sm:grid-cols-2">
					{articles.map((a) => (
						<li key={a.slug}>
							<NavLink
								to={`/blog/${a.slug}`}
								className="blog-card esc-card esc-lift group flex h-full flex-col gap-3 p-5 sm:p-6 bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
							>
								<h2 className="text-lg font-black leading-snug text-gray-900 dark:text-white group-hover:text-accent transition-colors">{a.title}</h2>
								<p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed flex-1">{a.description}</p>
								<time dateTime={a.date} className="text-xs text-gray-400">{formatBlogDate(a.date)}</time>
							</NavLink>
						</li>
					))}
				</ul>
			)}
		</div>
	);
};

export default BlogPage;
