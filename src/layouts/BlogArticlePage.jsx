import { NavLink, useParams } from 'react-router-dom';
import { articleSchema, formatBlogDate, useBlogArticle, useBlogHead } from '../hooks/useBlogData';
import NotFoundPage from './NotFoundPage';
import './escrow.css';
import './premium.css';
import './public.css';
import './blog.css';

const BlogArticlePage = () => {
	const { slug } = useParams();
	const { status, article } = useBlogArticle(slug);
	useBlogHead({
		path: `/blog/${slug}`,
		title: article ? `${article.title} — Блог TgSell` : '',
		description: article?.description || '',
		type: 'article',
		schema: articleSchema(article),
	});

	if (status === 'not_found') return <NotFoundPage />;

	return (
		<div className="esc-page prm-pub blog-page relative pt-24 md:pt-32 pb-12 max-w-3xl mx-auto px-4">
			<div className="esc-bg esc-bg-short" aria-hidden="true"><span className="esc-grid" /><span className="esc-blob esc-blob-1" /><span className="esc-blob esc-blob-2" /></div>
			<nav aria-label="Навігація" className="mb-6">
				<NavLink to="/blog" className="text-sm font-semibold text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 rounded">← Усі статті</NavLink>
			</nav>
			{status === 'loading' && <p className="text-sm text-gray-400" role="status">Завантаження…</p>}
			{status === 'error' && <p className="text-sm text-gray-500 dark:text-gray-400" role="alert">Не вдалося завантажити статтю. Спробуйте оновити сторінку.</p>}
			{status === 'ok' && article && (
				<article className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-6 sm:p-10 shadow-sm dark:shadow-neon">
					<header className="mb-8">
						<h1 className="esc-title text-2xl sm:text-4xl font-black leading-tight text-gray-900 dark:text-white mb-3 break-words">{article.title}</h1>
						<time dateTime={article.date} className="text-xs text-gray-400">{formatBlogDate(article.date)}</time>
					</header>
					{/* html comes from the server's safe markdown renderer (raw HTML disabled, URL whitelist). */}
					<div className="blog-body" dangerouslySetInnerHTML={{ __html: article.html }} />
					<aside className="mt-10 pt-6 border-t border-gray-100 dark:border-card-border flex flex-wrap gap-3">
						<NavLink to="/catalog" className="font-semibold bg-gradient-to-r from-emerald-500 to-green-500 text-white px-5 py-2.5 rounded-xl text-sm hover:shadow-lg hover:shadow-green-500/25 transition-all">Каталог каналів</NavLink>
						<NavLink to="/sell" className="font-semibold text-accent border border-accent/30 hover:bg-accent/10 px-5 py-2.5 rounded-xl text-sm transition-all">Продати канал</NavLink>
					</aside>
				</article>
			)}
		</div>
	);
};

export default BlogArticlePage;
