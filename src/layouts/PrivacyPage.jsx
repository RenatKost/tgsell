import { motion } from 'framer-motion';

const Section = ({ title, children }) => (
  <div className="mb-8">
    <h2 className="text-lg font-black text-gray-900 dark:text-white mb-3 flex items-center gap-2">
      <span className="w-1 h-5 rounded-full bg-accent flex-shrink-0" />
      {title}
    </h2>
    <div className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed space-y-2 pl-3">
      {children}
    </div>
  </div>
);

const PrivacyPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4 }}
    className="py-12 max-w-3xl mx-auto"
  >
    <div className="mb-10">
      <span className="inline-block bg-accent/10 border border-accent/20 text-accent text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">Документ</span>
      <h1 className="text-3xl font-black text-gray-900 dark:text-white mb-2">Політика конфіденційності</h1>
      <p className="text-sm text-gray-400">Редакція від 1 квітня 2025 р. · TgSell</p>
    </div>

    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-8 shadow-sm dark:shadow-neon">

      <Section title="1. Загальні положення">
        <p>Ця Політика конфіденційності описує, як платформа <strong>TgSell</strong> (далі — «Платформа», «Ми») збирає, використовує та захищає персональні дані користувачів (далі — «Користувач», «Ви»).</p>
        <p>Користуючись Платформою, ви погоджуєтесь з умовами цієї Політики.</p>
      </Section>

      <Section title="2. Які дані ми збираємо">
        <p><strong>При авторизації через Telegram:</strong> Telegram ID, ім'я, username, аватар (якщо публічний).</p>
        <p><strong>При авторизації через Google:</strong> email-адреса, ім'я, Google ID.</p>
        <p><strong>При використанні Платформи:</strong> IP-адреса, дані браузера, дії в системі (перегляди, угоди, ставки), USDT-адреса гаманця (якщо надана).</p>
        <p><strong>Статистика каналів:</strong> метрики Telegram-каналів, виставлених на продаж (підписники, охоплення, ER), — збираються автоматично через Telegram API.</p>
      </Section>

      <Section title="3. Мета використання даних">
        <p>— Авторизація та ідентифікація на Платформі;</p>
        <p>— Проведення угод купівлі-продажу каналів;</p>
        <p>— Надсилання сповіщень через Telegram-бота;</p>
        <p>— AI-аналіз каналів (дані передаються в знеособленому вигляді до Groq API);</p>
        <p>— Виявлення шахрайських дій та захист від зловживань;</p>
        <p>— Покращення якості сервісу та аналіз використання.</p>
      </Section>

      <Section title="4. Передача даних третім сторонам">
        <p>Ми не продаємо і не передаємо персональні дані третім особам, за винятком:</p>
        <p>— <strong>Groq API</strong> — для AI-аналізу каналів (без персональних даних);</p>
        <p>— <strong>TRON/TronPy</strong> — при проведенні USDT-транзакцій (лише адреси гаманців);</p>
        <p>— Правоохоронні органи — у разі законної вимоги.</p>
      </Section>

      <Section title="5. Зберігання та захист">
        <p>Дані зберігаються на захищених серверах Railway (EU region). Ми використовуємо JWT-токени з обмеженим терміном дії, HTTPS-з'єднання та обмежений доступ до бази даних.</p>
        <p>Паролі не зберігаються — авторизація виключно через OAuth (Telegram / Google).</p>
      </Section>

      <Section title="6. Права Користувача">
        <p>Ви маєте право:</p>
        <p>— Запросити видалення облікового запису та всіх пов'язаних даних;</p>
        <p>— Отримати копію своїх даних;</p>
        <p>— Відкликати згоду на обробку даних.</p>
        <p>Для реалізації прав зверніться: <a href="https://t.me/renat_kos" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">@renat_kos</a></p>
      </Section>

      <Section title="7. Cookie та локальне сховище">
        <p>Платформа використовує localStorage для зберігання JWT-токенів авторизації та налаштувань теми. Cookie не використовуються для відстеження.</p>
      </Section>

      <Section title="8. Зміни Політики">
        <p>Ми залишаємо за собою право оновлювати цю Політику. Про суттєві зміни повідомляємо через Telegram-бота. Актуальна версія завжди доступна на цій сторінці.</p>
      </Section>

      <Section title="9. Контакти">
        <p>З питань конфіденційності звертайтесь: <a href="https://t.me/renat_kos" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">@renat_kos</a></p>
      </Section>
    </div>
  </motion.div>
);

export default PrivacyPage;