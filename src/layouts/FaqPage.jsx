import { motion } from 'framer-motion';
import { NavLink } from 'react-router-dom';

const Section = ({ title, children }) => (
  <div className="mb-8">
    <h2 className="text-lg font-black text-gray-900 dark:text-white mb-3 flex items-center gap-2">
      <span className="w-1 h-5 rounded-full bg-violet-400 flex-shrink-0" />
      {title}
    </h2>
    <div className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed space-y-2 pl-3">
      {children}
    </div>
  </div>
);

const FaqPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4 }}
    className="py-12 max-w-3xl mx-auto"
  >
    <div className="mb-10">
      <span className="inline-block bg-violet-400/10 border border-violet-400/20 text-violet-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">Довідка</span>
      <h1 className="text-3xl font-black text-gray-900 dark:text-white mb-2">Часті запитання (FAQ)</h1>
      <p className="text-sm text-gray-400">Як купувати й продавати Telegram-канали на TgSell</p>
    </div>

    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-8 shadow-sm dark:shadow-neon">

      <Section title="1. Як купити канал">
        <p>1. Відкрийте <NavLink to="/catalog" className="text-accent hover:underline">каталог</NavLink> або <NavLink to="/auction" className="text-accent hover:underline">аукціон</NavLink> і оберіть канал.</p>
        <p>2. Авторизуйтесь (Telegram або Google) і розпочніть угоду на сторінці каналу.</p>
        <p>3. На сторінці угоди обидві сторони підтверджують готовність.</p>
        <p>4. Покупець переказує USDT (мережа TRC-20) на унікальну адресу ескроу-гаманця угоди. Оплата перевіряється автоматично.</p>
        <p>5. Після зарахування коштів продавець передає права власника каналу в Telegram; обидві сторони підтверджують передачу на TgSell.</p>
        <p>6. Продавець вказує свою USDT (TRC-20) адресу та отримує виплату (мінус комісія платформи).</p>
        <p>Етапи угоди на сторінці deal: готовність → оплата → передача → виплата → завершено.</p>
      </Section>

      <Section title="2. Як продати канал">
        <p>1. Авторизуйтесь і перейдіть на сторінку <NavLink to="/sell" className="text-accent hover:underline">«Продати»</NavLink> (або продаж бандлу).</p>
        <p>2. Додайте канал, вкажіть ціну та необхідні дані. Оголошення проходить модерацію (зазвичай протягом 24 годин згідно з офертою).</p>
        <p>3. Коли покупець розпочинає угоду — підтвердіть готовність, дочекайтесь оплати на ескроу, передайте власність каналу в Telegram і підтвердіть передачу на TgSell.</p>
        <p>4. Після підтвердження передачі обома сторонами вкажіть гаманець TRC-20 і отримайте кошти за вирахуванням 3% комісії.</p>
      </Section>

      <Section title="3. Ескроу USDT TRC-20">
        <p>Усі угоди проводяться через ескроу-сервіс платформи:</p>
        <p>— Покупець сплачує повну суму угоди в USDT лише через мережу <strong>TRC-20</strong> на адресу ескроу конкретної угоди.</p>
        <p>— Кошти зберігаються на ескроу до завершення переходу прав на канал.</p>
        <p>— Після підтвердження передачі платформа звільняє кошти продавцю (мінус комісія).</p>
        <p>— Переводьте лише USDT TRC-20: інші мережі або токени можуть призвести до втрати коштів. Платформа не відповідає за затримки мережі TRON.</p>
        <p>— Комісія мережі TRON зазвичай становить близько 1–2 TRX (орієнтовно 0.1–0.2 USDT) і сплачується окремо від суми угоди.</p>
      </Section>

      <Section title="4. Комісія платформи">
        <p>За кожну успішно завершену угоду платформа утримує <strong>комісію 3%</strong> від суми угоди.</p>
        <p>Комісія вираховується з виплати продавцю. Покупець сплачує повну суму угоди на ескроу.</p>
        <p>При участі в аукціоні додаткових зборів, крім цієї 3% комісії при закритті угоди, немає.</p>
      </Section>

      <Section title="5. Передача власності каналу в Telegram (покроково)">
        <p><strong>Що робить продавець після оплати на ескроу:</strong></p>
        <p>1. Відкрийте Telegram → налаштування каналу (Channel / Channel info).</p>
        <p>2. Перейдіть до Administrators (Адміністратори).</p>
        <p>3. Оберіть Transfer Ownership (Передати права власника) і вкажіть акаунт покупця.</p>
        <p>4. Підтвердіть передачу паролем двофакторної автентифікації (2FA), якщо Telegram цього вимагає.</p>
        <p>5. На сторінці угоди TgSell натисніть «Підтвердити передачу».</p>
        <p><strong>Що робить покупець:</strong></p>
        <p>1. Прийміть запрошення на передачу власності в Telegram (якщо потрібно).</p>
        <p>2. Переконайтесь, що ви стали власником каналу.</p>
        <p>3. На сторінці угоди натисніть «Підтвердити отримання».</p>
        <p><strong>Обмеження Telegram і типові строки:</strong></p>
        <p>— Для передачі власності Telegram зазвичай вимагає увімкнену <strong>двофакторну автентифікацію (2FA)</strong> на акаунті поточного власника; без 2FA передача може бути недоступна.</p>
        <p>— Обидва акаунти мають бути активними; покупець повинен мати можливість прийняти передачу в Telegram.</p>
        <p>— Telegram може обмежувати повторну передачу того самого каналу протягом певного періоду після попередньої зміни власника — якщо кнопка Transfer Ownership недоступна, перевірте обмеження в інтерфейсі Telegram або зверніться до підтримки.</p>
        <p>— Сама передача в Telegram зазвичай займає від кількох хвилин до кількох годин (залежить від дій сторін і підтверджень Telegram). На TgSell наступний крок (виплата) відкривається після підтвердження передачі обома сторонами.</p>
        <p>— Не видаляйте канал і не знімайте права адміна «вручну» замість офіційної Transfer Ownership — для угоди потрібна саме передача власності.</p>
      </Section>

      <Section title="6. Спори та повернення">
        <p>Якщо після оплати виникла проблема з передачею каналу, покупець може відкрити <strong>спір</strong> на сторінці угоди (кнопка «Спір»). Статус угоди змінюється на «disputed», і питання розглядає адміністратор.</p>
        <p>Також у чаті угоди можна викликати адміністратора.</p>
        <p>Контакт для спорів: <a href="https://t.me/tgsell_support_bot" className="text-accent hover:underline" target="_blank" rel="noopener noreferrer">@tgsell_support_bot</a>.</p>
        <p>Рішення адміністратора в рамках платформи є остаточним (див. <NavLink to="/oferta" className="text-accent hover:underline">публічну оферту</NavLink>). Повернення з ескроу можливе за рішенням адмін-модерації, якщо угоду скасовано або спір вирішено на користь покупця — конкретний результат залежить від обставин угоди.</p>
        <p>Платформа виступає посередником і не гарантує якість контенту чи аудиторії каналу після угоди.</p>
      </Section>

      <Section title="7. Корисні посилання">
        <p><NavLink to="/oferta" className="text-accent hover:underline">Публічна оферта</NavLink> · <NavLink to="/privacy" className="text-accent hover:underline">Політика конфіденційності</NavLink> · <NavLink to="/contacts" className="text-accent hover:underline">Контакти</NavLink></p>
      </Section>
    </div>
  </motion.div>
);

export default FaqPage;
