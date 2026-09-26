# بحث التنفيذ: Freqtrade + FreqAI على Bybit (من مصر، برصيد ~2$)

> تاريخ البحث: 26 سبتمبر 2026. كل الأرقام تتغير، فراجعها قبل ما تشغّل بفلوس حقيقية.
> ملحوظة مهمة: مواقع Bybit كلها (bybit.com و bybit.global و announcements و api.bybit.com) كانت **محجوبة جغرافيًا أو بترجع 503** من جهاز البحث. عشان كده معلومات Bybit جاية من: توثيق الـ API الرسمي على `bybit-exchange.github.io`، وقناة Bybit API Announcements على تيليجرام، ومقتطفات بحث من صفحات Bybit الرسمية. أي حاجة ما اتأكدتش منها مكتوب جنبها **(غير مؤكد)**.

---

## الخلاصة

- **مصر مش في قائمة الدول المحظورة الرسمية عند Bybit** (القائمة فيها أمريكا، الصين، هونج كونج، سنغافورة، كندا، إيران، سوريا، السودان، أوزبكستان، كوريا الشمالية، كوبا، ومناطق في أوكرانيا…). يعني نظريًا Spot و Derivatives متاحين. **لكن** قانون البنك المركزي المصري رقم 194 لسنة 2020 (مادة 206) بيمنع تداول العملات المشفرة بدون ترخيص من البنك المركزي، وده خطر قانوني عليك انت شخصيًا، مش على Bybit. بعض المواقع (غير رسمية) بتقول إن المشتقات ممكن تبقى مقيدة لمصر، وده **غير مؤكد**.
- **الرسوم (المستوى العادي / Non-VIP):** Spot = **0.10% Maker و 0.10% Taker**. عقود USDT الدائمة = **0.02% Maker و 0.055% Taker**.
- **أقل أوردر:** Spot عن طريق API = **5 USDT** (من 21 يناير 2025، كان 1 USDT). العقود الدائمة: أقل قيمة اسمية **5 USDT** مع حد أدنى للكمية (BTCUSDT = 0.001 BTC ≈ **84$** بسعر النهارده).
- **هل حساب 2$ يقدر يعمل أوردر؟** على الـ Spot عن طريق البوت: **لأ** (محتاج 5$ على الأقل، والأفضل 6–7$ عشان الرسوم والتقريب). على العقود: تقنيًا ممكن برافعة مالية على عملة صغيرة، لكن ده **خطير جدًا** على حساب صغير، ومش على BTC (محتاج 84$ اسميًا). **الخلاصة: 2$ ينفعوا للـ dry-run والتعلم بس.**
- **Freqtrade:** آخر إصدار مستقر **2026.8 (31 أغسطس 2026)**. محتاج **Python 3.11 أو أحدث** (مدعوم 3.11 / 3.12 / 3.13 / 3.14). Bybit مدعوم Spot و Futures (الـ Futures في وضع **isolated** بس)، ومستحسن **حساب فرعي (Sub-account) مخصص للبوت**، خصوصًا مع Unified Account.
- **البيانات:** `download-data` بيشتغل مع OKX، وتاريخ BTC/USDT على فريم ساعة بيرجع لحد **يناير 2018** (اتأكدت بنفسي من API بتاع OKX). بيانات بورصة تانية كويسة كـ"تقريب" للباك تست على العملات الكبيرة، بس مش بديل كامل.
- **FreqAI:** ابدأ بـ **LightGBMRegressor** (هو الموديل المستخدم في المثال الرسمي). والتوثيق بيقول صراحة إن **الاستراتيجية المثال مش معمولة للتشغيل الحقيقي (Not for production)**.
- **التشغيل 24/7:** أرخص حاجة معقولة: جهازك في البيت / Raspberry Pi (تكلفة كهرباء بس)، أو VPS زي Hetzner CX23 بـ **5.49€/شهر** (أسعار بعد زيادة 15 يونيو 2026). **Bybit بيرفض أي IP من أمريكا أو الصين (403)** — فمتختارش سيرفر في أمريكا.
- **الأمان:** مفتاح API **من غير صلاحية سحب**، **مربوط بـ IP** (لو مش مربوط بيخلص بعد 90 يوم)، وعلى **حساب فرعي** للبوت بس.

---

## 1) Bybit ومصر: هل متاح؟

**القائمة الرسمية للدول المحظورة (Service Restricted Countries):**
حسب صفحة مركز المساعدة الرسمية (من مقتطف البحث، لأن الصفحة نفسها كانت بترجع 503):
> Bybit does not offer services or products to Users in … the United States, the Chinese Mainland, Hong Kong, Singapore, Canada, North Korea, Cuba, Iran, Uzbekistan, Russian-controlled regions of Ukraine (Crimea, Donetsk, Rostov, Luhansk), Sevastopol, Sudan, Syria, and (for Bybit Virtual Asset Platform Operator LLC only) Dubai.

- **مصر مش موجودة في القائمة** [1]. موقع Datawallet (آخر تحديث 2 أغسطس 2026) بيأكد نفس الكلام: مصر مش في القائمة المستبعدة [2].
- **Spot و Derivatives:** مفيش في الصفحة الرسمية أي قيد خاص بمصر على المشتقات. فيه موقع واحد على الأقل (BitDegree/نتائج بحث عامة) بيلمّح إن مصر عليها قيود — ده **غير مؤكد ومتعارض** مع القائمة الرسمية [3]. **الحل العملي:** بعد ما تعمل الحساب والـ KYC، افتح صفحة Derivatives وشوف هل بيسمحلك تفعّلها ولا لأ.
- **ملحوظة:** لو دخلت من دولة محظورة، Bybit بيعملك تسجيل خروج تلقائي [1]. وده بيأثر على اختيار مكان السيرفر (شوف البند 8).

**الجانب القانوني في مصر (مهم):**
- قانون البنك المركزي والجهاز المصرفي رقم 194 لسنة 2020، **مادة 206**، بتمنع إصدار أو تداول أو الترويج للعملات المشفرة من غير ترخيص من البنك المركزي، والعقوبات فيها حبس و/أو غرامة من 1 لـ 10 مليون جنيه [4][5]. البنك المركزي نشر أكتر من تحذير رسمي (منها سبتمبر 2022 ومارس 2023) [6].
- ده مش استشارة قانونية، بس لازم تبقى عارف إن الخطر القانوني موجود حتى لو Bybit نفسه بيقبل المصريين.

## 2) رسوم التداول (المستوى العادي Non-VIP)

| السوق | Maker | Taker |
|---|---|---|
| Spot (الأزواج العادية) | 0.10% | 0.10% |
| Spot (Adventure Zone) | 0.20% | 0.20% |
| عقود USDT الدائمة / Futures | 0.02% | 0.055% |

المصادر: صفحات Bybit الرسمية "Trading Fee Structure" و"Spot Trading: Fees Explained" و"Futures Contracts: Fees Explained" (عن طريق مقتطفات البحث، سبتمبر 2026) [7][8][9]، ومؤكد من مراجعات خارجية (BitDegree 2026) [10].

**يعني إيه عمليًا؟** صفقة Spot كاملة (دخول + خروج) بتكلفك تقريبًا **0.2%**. في الباك تست حط `"fee": 0.001` للـ Spot. للعقود، لو بتدخل Market بتدفع 0.055% في كل ناحية (~0.11% رايح جاي) + Funding.

## 3) أقل قيمة للأوردر، وهل 2$ تكفي؟

**Spot:**
- من **21 يناير 2025 الساعة 8 صباحًا UTC**: أقل قيمة أوردر (`minOrderAmt`) للتداول عن طريق **API** اتغيرت من **1 USDT إلى 5 USDT**. (بوتات Bybit الداخلية والـ brokers مش متأثرين) [11].
- توثيق الـ API الرسمي، مثال BTCUSDT Spot: `"minOrderAmt": "5"`، و`minOrderQty` بقى **deprecated** ومش بيتشيك عليه [12].
- ETH/USDT و SOL/USDT: **ما قدرتش أتأكد من القيمة الدقيقة** (الـ API محجوب من هنا)، لكن القاعدة العامة للـ API هي 5 USDT، ومن المتوقع إنها نفس القيمة للأزواج الكبيرة **(غير مؤكد)**. فيه إعلانات تعديل دورية (منها 16 مارس 2026 و 22 أبريل 2026) لبعض الأزواج — تفاصيلها ما اتقرتش [13].
- Freqtrade نفسه بيحسب الـ minimum stake من بيانات السوق وبيضيف هامش أمان، فعمليًا محتاج أكتر شوية من 5$ لكل صفقة.

**عقود USDT الدائمة:**
- Bybit فرض حد أدنى للقيمة الاسمية (`minNotionalValue`) على عقود USDT Perpetual من 28 مارس 2024، والمثال في التوثيق = **5 USDT** [12][14].
- وكمان فيه حد أدنى للكمية (`minOrderQty`)، مثال BTCUSDT = **0.001 BTC** [12]. بسعر BTC النهارده (~84,225$ على OKX يوم 26/9/2026) ده ≈ **84$ قيمة اسمية**.
- ETHUSDT و SOLUSDT: الكمية الدنيا المعروفة تاريخيًا 0.01 ETH (≈27$) و 0.1 SOL (≈12$) — **غير مؤكد** للنهارده.
- مقتطف بحث بيقول إن بعض العقود اتغير حدها من 5 إلى 100 USDT — **غير مؤكد** أي عقود بالظبط [14].

**هل 2$ تقدر تعمل أوردر؟**
- **Spot عن طريق البوت: لأ.** 2$ أقل من 5$.
- **Futures:** الـ margin المطلوب = القيمة الاسمية ÷ الرافعة. يعني أوردر 5$ برافعة 5x محتاج ~1$ margin + رسوم. تقنيًا ممكن على عملات صغيرة، لكن رصيد 2$ هيتصفّى (liquidation) من أول حركة عكسية، ومفيش مساحة للرسوم أو إدارة المخاطر. **مش منصوح بيه.**
- **التوصية:** ابقى على `dry_run: true` (رصيد وهمي) أو **Bybit Demo Trading** (مدعوم في Freqtrade بـ `exchange.demo_trading: true` بمفاتيح API منفصلة) لحد ما النتايج تبقى مقنعة، وبعدها زوّد الرصيد لحاجة زي 20–50$ على الأقل.

## 4) Freqtrade: الإصدار، Python، ودعم Bybit

- **آخر إصدار مستقر:** `2026.8`، نزل على PyPI يوم **31 أغسطس 2026** (اللي قبله 2026.7 في 31 يوليو، و 2026.6 في 29 يونيو) [15]. نفس الرقم في `freqtrade/__init__.py` على فرع `stable` [16].
- **Python:** `requires-python = ">=3.11"`، والإصدارات المذكورة رسميًا: **3.11، 3.12، 3.13، 3.14** [16][17].
- **Bybit في توثيق Freqtrade** [18]:
  - مدعوم في قائمة Spot وقائمة Futures (وفيه كمان "Bybit EU" للـ Spot بس) [19].
  - **Futures مدعوم في وضع isolated بس.** Freqtrade بيحط الحساب (أو الحساب الفرعي) على **One-way Mode** أول ما يشتغل، ولو غيرته يدويًا ممكن يحصل أخطاء.
  - **Stoploss on exchange:** مدعوم في الـ **Futures بس** (limit أو market)، **مش مدعوم في Spot**.
  - `time_in_force`: GTC, FOK, IOC, PO.
  - **تحذير Unified accounts:** "Freqtrade assumes accounts to be dedicated to the bot… we recommend one subaccount per bot. This is especially important when using unified accounts." يعني ماتعملش صفقات يدوي على نفس الحساب، ولا تشغل بوتين على نفس الحساب.
  - Bybit مش بيدي تاريخ Funding rate، فالحساب بتاع الـ funding في الـ live بيستخدم نفس طريقة الـ dry-run.
  - صلاحيات مفتاح الـ API للـ Futures live: **Read-write** + **Contract – Orders** + **Contract – Positions**. والتوثيق "strongly recommend" تربط المفتاح بالـ IP.
  - **Demo mode:** `"exchange": {"demo_trading": true}` بمفاتيح من صفحة الـ Demo. **مينفعش مع dry-run في نفس الوقت.**
  - في الكود (`freqtrade/exchange/bybit.py`): `fetchOrder` مقفول على الـ Spot "Unless the account is unified"، وده سبب إضافي تستخدم Unified Account على حساب فرعي [20].
- **الكونفيج الأساسي لـ Bybit:** `"exchange": {"name": "bybit", "key": "...", "secret": "..."}` — مفيش passphrase (عكس OKX). للـ Futures: `"trading_mode": "futures", "margin_mode": "isolated"`.

## 5) تحميل البيانات من OKX واستخدامها للباك تست

- **`download-data` بيشتغل مع OKX:** OKX مدعوم Spot و Futures [19]. أمر مثال:
  `freqtrade download-data --exchange okx --pairs BTC/USDT ETH/USDT SOL/USDT --timeframes 1h --timerange 20180101-`
- **تحذير في التوثيق:** "OKX only provides 100 candles per api call…" [18]. في الكود الحالي الحد بقى **300 شمعة** للـ spot/futures، و100 للـ mark/premium التاريخية [21]. ده بيخلي التحميل أبطأ بس Freqtrade بيعمل pagination فبيجيب التاريخ كله.
- **قد إيه بيرجع ورا (فريم 1h)؟** جربت API بتاع OKX (`/api/v5/market/history-candles`) بنفسي يوم 26/9/2026:
  - **BTC-USDT:** أول شمعة ساعة موجودة في **منتصف يناير 2018 تقريبًا** (موجود قبل 15/1/2018، ومفيش بيانات قبل 3/1/2018).
  - **SOL-USDT:** فيه بيانات من أول 2021 على الأقل (قبل كده العملة ماكانتش مدرجة).
- **Futures على OKX:** شموع MARK متاحة لآخر ~3 شهور بس، فالباك تست للعقود قبل كده بيبقى فيه انحراف بسيط في حساب الـ funding [18].
- **هل بيانات بورصة تانية تنفع بديل لـ Bybit؟**
  - للأزواج الكبيرة السايلة (BTC, ETH, SOL مقابل USDT) على فريم **1h**، الأسعار بين البورصات الكبيرة متقاربة جدًا (فرق الأسعار بيتقفل بسرعة بالـ arbitrage)، فالبيانات **تقريب معقول** لاختبار فكرة الاستراتيجية. (ده استنتاج منطقي، مش من توثيق رسمي.)
  - **الاختلافات:** الـ volume مختلف (أي مؤشر معتمد على الحجم هيتأثر)، الرسوم مختلفة (حط رسوم Bybit في الكونفيج)، الـ funding rates مختلفة في العقود، وفيه wicks/شمعات شاذة مختلفة على الفريمات الصغيرة.
  - **التوصية:** طوّر وجرّب على بيانات OKX، وبعدين من جهازك في مصر (Bybit مش محجوب هناك) حمّل بيانات Bybit نفسها لآخر فترة واعمل باك تست تأكيدي عليها. (تاريخ بيانات Bybit Spot الـ 1h بيرجع لحد إمتى: **غير مؤكد** — ماقدرتش أوصل للـ API.)

## 6) استراتيجيات مفتوحة المصدر للمقارنة (Benchmarks)

من الريبو الرسمي `freqtrade/freqtrade-strategies` (مسار `user_data/strategies/`، تأكدت إن الملفات موجودة يوم 26/9/2026) [22]:

| الملف | الفكرة | الفريم | ملاحظات |
|---|---|---|---|
| `Strategy001.py` | تقاطع EMA20/EMA50 + Heikin-Ashi للدخول، EMA50/EMA100 للخروج | 5m | stoploss -10%، بسيطة جدًا |
| `Strategy002.py` | RSI < 30 + Stochastic + Bollinger، خروج بـ Fisher RSI + SAR | 5m | mean reversion |
| `Supertrend.py` | 3 مؤشرات Supertrend للدخول و3 للخروج (معمول لها hyperopt) | **1h** | stoploss -26.5%، مناسبة لفريم الساعة |
| `berlinguyinca/ADXMomentum.py` | ADX + Momentum + DI | — | استراتيجية كلاسيكية شائعة |
| `futures/FSupertrendStrategy.py` | نسخة Supertrend للعقود (long/short) | — | لو هتجرب Futures |

كمان في الريبو الرئيسي: `freqtrade/templates/sample_strategy.py` (الـ `SampleStrategy`) — مرجع بسيط كويس.

- README الريبو بيقول: "They also mostly should serve as a starting point for your own strategies, not as 'ready to use' strategies" و"results will heavily depend on the pairs, timeframe and timerange" [22].
- **الفكرة:** أي موديل FreqAI لازم يغلب على الأقل الـ Buy & Hold + `Supertrend` + `Strategy001` على نفس الأزواج ونفس الفترة ونفس الرسوم، وإلا مالوش لازمة.

## 7) FreqAI: الموديل والإعدادات والتحذير

- **الموديل المقترح للبداية:** `LightGBMRegressor` — ده الموديل اللي بيستخدمه الأمر المثال في التوثيق:
  `freqtrade trade --config config_examples/config_freqai.example.json --strategy FreqaiExampleStrategy --freqaimodel LightGBMRegressor --strategy-path freqtrade/templates` [23].
  متاح كمان `LightGBMClassifier`, `XGBoostRegressor/Classifier`, ونماذج PyTorch و Reinforcement Learning [24]. الـ Classifier لازم تعرّف `self.freqai.class_names` (مثلًا "up"/"down").
- **التثبيت:** وافق على تثبيت FreqAI أثناء الـ install أو `pip install -r requirements-freqai.txt`. على Docker استخدم `freqtradeorg/freqtrade:stable_freqai`. **CatBoost مش بيتثبت على أجهزة ARM الضعيفة (Raspberry Pi)** [23].
- **أهم الباراميترات** [25] (والقيم من `config_freqai.example.json` الرسمي [26]):

| الباراميتر | المعنى | قيمة المثال |
|---|---|---|
| `train_period_days` | **إجباري.** عدد أيام بيانات التدريب (عرض النافذة المتحركة) | 15 |
| `backtest_period_days` | **إجباري.** كام يوم يتنبأ بالموديل قبل ما يحرّك النافذة ويعيد التدريب في الباك تست (ممكن كسور، بس الـ timerange بيتقسم عليه = عدد مرات التدريب) | 7 |
| `label_period_candles` | كام شمعة في المستقبل الـ label بيتحسب عليها (جوه `feature_parameters`) | 20 |
| `identifier` | **إجباري.** اسم فريد للموديل (لحفظ/تحميل الموديلات) | "unique-id" |
| `live_retrain_hours` | كل قد إيه يعيد التدريب في dry/live (0 = بأسرع ما يمكن) | 0 |
| `include_timeframes` | فريمات إضافية للـ features | 3m, 15m, 1h |
| `include_corr_pairlist` | عملات مرتبطة تتضاف كـ features | BTC, ETH |
| `DI_threshold` / `use_SVM_to_remove_outliers` | إزالة القيم الشاذة | 0.9 / true |
| `data_split_parameters.test_size` | نسبة بيانات الاختبار | 0.33 |

  ملحوظة: المثال الرسمي معمول على فريمات صغيرة (3m) وأزواج Futures. لمشروعنا على 1h، زوّد `train_period_days` (مثلًا 60–120) عشان يبقى فيه عدد شموع كفاية — ده اقتراح مني مش من التوثيق.
- **التحذير الرسمي عن الاستراتيجية المثال** (نص التوثيق) [23]:
  > **Not for production** — The example strategy provided with the Freqtrade source code is designed for showcasing/testing a wide variety of FreqAI features. It is also designed to run on small computers so that it can be used as a benchmark between developers and users. It is *not* designed to be run in production.

## 8) أرخص طرق لتشغيل البوت 24/7

| الخيار | التكلفة التقريبية | ملاحظات |
|---|---|---|
| جهازك في البيت (PC/لابتوب) | كهرباء بس | لازم يفضل شغال + النت مستقر. IP البيت غالبًا متغير → صعب تربط مفتاح الـ API بـ IP ثابت. |
| Raspberry Pi 4/5 (4–8GB) | سعر الجهاز مرة واحدة + كهرباء قليلة | Freqtrade العادي شغال كويس؛ FreqAI تقيل عليه (التدريب بطيء) و**CatBoost مش مدعوم على ARM** [23]. نفس مشكلة الـ IP. |
| Hetzner Cloud CX23 (2 vCPU / 4GB / 40GB) | **5.49€/شهر** (بدون ضريبة، ألمانيا/فنلندا) | الأسعار اتزودت من 3.99€ يوم 15 يونيو 2026 [27]. CAX11 (ARM) = 5.99€. + ممكن رسوم IPv4 إضافية. |
| Oracle Cloud Always Free (ARM) | مجاني | اتقلّص في يونيو 2026 من 4 OCPU/24GB لـ **2 OCPU/12GB**، والأماكن بتخلص كتير ("Out of capacity") [28]. خلي بالك من اختيار region مش أمريكي. |
| Contabo / DigitalOcean / Vultr وغيرهم | تقريبًا 4–7$/شهر | **ماتأكدتش من أسعارهم الحالية.** |

- **حجب Bybit للسيرفرات:** توثيق Bybit الرسمي: "IP addresses located in the US or Mainland China are restricted and will return a 403 Forbidden error" [29]. وفيه تقارير إن CloudFront بتاع Bybit بيحجب بعض نطاقات الـ cloud [30]. حتى جهاز البحث ده (غالبًا في أمريكا) اترفض بـ "CloudFront … block access from your country".
- **التوصية:** سيرفر في **أوروبا** (ألمانيا/فنلندا/هولندا) أو قريب زي الشرق الأوسط. **متستخدمش VPN للتحايل** على الحجب — ده ضد شروط Bybit وممكن يتقفل حسابك.
- **الأذكى للبداية:** شغّل الـ dry-run على جهازك في البيت (مجانًا). لما تقرر تدخل بفلوس، خد VPS أوروبي بـ IP ثابت واربط المفتاح عليه.
- ملحوظة: FreqAI بيحتاج RAM و CPU أكتر من Freqtrade العادي؛ 4GB RAM حد أدنى معقول لعدد قليل من الأزواج (تقدير، مش رقم رسمي).

## 9) أمان مفاتيح Bybit API

1. **ماتفعّلش صلاحية السحب (Withdrawal) أبدًا.** البوت محتاج بس: Read-write + Spot Trade (للـ Spot) أو Contract Orders + Contract Positions (للـ Futures) [18].
2. **اربط المفتاح بـ IP (IP whitelist):** توثيق Bybit: "An API key created without binding IP address(es) will expire after 90 days" [31]. يعني المفتاح المربوط بـ IP مش بيخلص، واللي مش مربوط بيخلص بعد 90 يوم. وFreqtrade نفسه "strongly recommend" الربط بـ IP [18]. (من فبراير 2026 تعديل الـ IP whitelist لمفاتيح الحساب الرئيسي بقى من المتصفح بس، مش من الـ API — ده من مصدر خارجي **غير مؤكد**.)
3. **حساب فرعي (Sub-account) للبوت:** Freqtrade بيوصي بحساب فرعي لكل بوت، خصوصًا مع Unified Account [18]. حوّل للحساب الفرعي بس المبلغ اللي مستعد تخسره. Bybit بيدعم مفاتيح API للحسابات الفرعية [32].
4. **فعّل 2FA (Google Authenticator)** على الحساب — مطلوب أصلًا لإنشاء المفتاح [33].
5. **احفظ المفاتيح برا Git:** حطها في ملف كونفيج منفصل متسجل في `.gitignore` أو في متغيرات بيئة (`FREQTRADE__EXCHANGE__KEY` و `FREQTRADE__EXCHANGE__SECRET`). مفاتيح الـ Demo منفصلة عن الحقيقية، ومفاتيح الـ Testnet منفصلة كمان (كل مفتاح لازم يتطابق مع الدومين بتاعه وإلا error 10003) [31].
6. **لو تسرّب المفتاح:** امسحه فورًا من صفحة API Management واعمل واحد جديد.

---

## المصادر

1. Bybit Help Center — Service Restricted Countries: https://www.bybit.com/en/help-center/article/Service-Restricted-Countries (مقتطف بحث، سبتمبر 2026؛ الصفحة رجعت 503 عند الفتح المباشر)
2. Datawallet — Bybit Supported and Restricted Countries (آخر تحديث 2 أغسطس 2026): https://www.datawallet.com/crypto/bybit-restricted-countries
3. BitDegree — Bybit Restricted Countries: https://www.bitdegree.org/crypto/tutorials/bybit-restricted-countries
4. Andersen Egypt — The Legality of Cryptocurrency in Egypt: https://eg.andersen.com/legality-cryptocurrency-in-egypt/
5. Lexology — Cryptocurrency legality in Egypt: https://www.lexology.com/library/detail.aspx?g=a21a3371-3157-4c46-8ab2-1e15e9a59450
6. البنك المركزي المصري — Warning Statements: https://www.cbe.org.eg/en/news-publications/news/2022/09/12/warning-statement و https://www.cbe.org.eg/en/news-publications/news/2023/03/08/warning-statement
7. Bybit — Trading Fee Structure: https://www.bybit.com/en/help-center/article/Trading-Fee-Structure (مقتطف بحث)
8. Bybit — Spot Trading: Fees Explained: https://www.bybit.com/en/help-center/article/Bybit-Spot-Fees-Explained (مقتطف بحث)
9. Bybit — Futures Contracts: Fees Explained: https://www.bybit.com/en/help-center/article/Perpetual-Futures-Contract-Fees-Explained (مقتطف بحث)
10. BitDegree — Bybit Fees 2026: https://www.bitdegree.org/crypto/tutorials/bybit-fees
11. Bybit API Announcements (Telegram) — Spot minOrderAmt 1 → 5 USDT من 21 يناير 2025: https://t.me/s/bybit_api_announcements?before=306 ، والإعلان: https://announcements.bybit.com/article/bybit-spot-adjustment-to-minimum-order-value-for-api-trading-bltc321af13dcc5254f/
12. Bybit API Docs — Get Instruments Info (V5): https://bybit-exchange.github.io/docs/v5/market/instrument (اتقرت 26/9/2026)
13. Bybit Announcement — Minimum order value update for spot and margin pairs (22 أبريل 2026): https://announcements.bybit.com/en/article/minimum-order-value-update-for-spot-and-margin-pairs---apr-22-2026-8-00am-utc-bltb75df624395ec458/ (العنوان بس، المحتوى ما اتقراش)
14. Bybit Announcement — Introducing Minimum Notional Value Requirement for Derivatives Trading: https://announcements.bybit.com/article/introducing-minimum-notional-value-requirement-for-derivatives-trading-blt5c48b4d341168a81/ (مقتطف بحث)
15. PyPI — freqtrade (2026.8، 31 أغسطس 2026): https://pypi.org/project/freqtrade/
16. Freqtrade `pyproject.toml` و `freqtrade/__init__.py` (فرع stable): https://github.com/freqtrade/freqtrade/blob/stable/pyproject.toml
17. Freqtrade Docs — Installation: https://www.freqtrade.io/en/stable/installation/
18. Freqtrade Docs — Exchange-specific Notes (Bybit, OKX): https://www.freqtrade.io/en/stable/exchanges/
19. Freqtrade Docs — Supported exchanges: https://www.freqtrade.io/en/stable/
20. Freqtrade source — `freqtrade/exchange/bybit.py`: https://github.com/freqtrade/freqtrade/blob/stable/freqtrade/exchange/bybit.py
21. Freqtrade source — `freqtrade/exchange/okx.py`: https://github.com/freqtrade/freqtrade/blob/stable/freqtrade/exchange/okx.py
22. freqtrade/freqtrade-strategies (README والملفات): https://github.com/freqtrade/freqtrade-strategies
23. Freqtrade Docs — FreqAI (Quick start, Not for production, Install): https://www.freqtrade.io/en/stable/freqai/
24. Freqtrade Docs — FreqAI Configuration: https://www.freqtrade.io/en/stable/freqai-configuration/
25. Freqtrade Docs — FreqAI Parameter table: https://www.freqtrade.io/en/stable/freqai-parameter-table/
26. `config_examples/config_freqai.example.json`: https://github.com/freqtrade/freqtrade/blob/stable/config_examples/config_freqai.example.json
27. Hetzner Docs — Price Adjustment 15 June 2026: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
28. InfoQ — Oracle Quietly Halves Free Tier Ampere A1 Limits (يوليو 2026): https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
29. Bybit API Docs — Integration Guidance: https://bybit-exchange.github.io/docs/v5/guide
30. QuotaGuard — Bybit API 403 on Cloud Platforms: https://www.quotaguard.com/blog/bybit-api-403-cloud-platform-cdn-block-fix
31. Bybit API Docs — FAQ (انتهاء المفتاح بعد 90 يوم بدون IP): https://bybit-exchange.github.io/docs/faq
32. Bybit API Docs — Create Sub UID API Key: https://bybit-exchange.github.io/docs/v5/user/create-subuid-apikey
33. Bybit Help Center — How to Create Your API Key: https://www.bybit.com/en/help-center/article/How-to-create-your-API-key
34. OKX Public API (تجربة مباشرة 26/9/2026 للتاريخ والأسعار): https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H
