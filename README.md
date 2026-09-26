# Our-Bank: تجربة بوت تداول بالذكاء الاصطناعي

تجربة منظمة لاختبار: هل بوت تداول (بقواعد ثابتة أو بالـ AI) يقدر يكسب فعلاً بعد التكاليف؟
المبني على [Freqtrade](https://github.com/freqtrade/freqtrade) و FreqAI. **كل حاجة هنا dry-run / backtest، مفيش فلوس حقيقية.**

- النتايج المجمعة: [`reports/SUMMARY.md`](reports/SUMMARY.md)
- البحث: [`docs/research-implementation.md`](docs/research-implementation.md)
- طريقة الشغل والقواعد: [`CLAUDE.md`](CLAUDE.md)

## المحتوى

| المسار | فيه إيه |
|---|---|
| `strategies/EmaCrossBaseline.py` | تقاطع متوسطات EMA مع فلتر اتجاه |
| `strategies/RsiMeanReversionBaseline.py` | شراء عند تشبع بيعي RSI في اتجاه صاعد |
| `strategies/DonchianBreakoutBaseline.py` | كسر أعلى سعر في N شمعة (تتبع اتجاه) |
| `strategies/FreqAIStrategy.py` | LightGBM يتوقع العائد في الـ 12 ساعة الجاية، بيتدرب walk-forward |
| `config/config.backtest.json` | إعدادات الباك تست (100 USDT وهمي، رسوم 0.1%) |
| `config/config.freqai.json` | إعدادات FreqAI |
| `config/config.bybit.dryrun.json` | قالب تشغيل dry-run لايف على Bybit |
| `scripts/` | إعداد، تشغيل الباك تستات، فحص look-ahead، وتلخيص النتايج |
| `reports/` | النتايج |

## التشغيل

محتاج Python 3.11+.

```bash
scripts/setup.sh            # venv + Freqtrade 2026.8 + تنزيل البيانات (OKX)
scripts/run_baselines.sh    # الاستراتيجيات البسيطة: فترة تطوير + فترة اختبار، رسوم 0.1% و 0.2%
scripts/run_lookahead.sh    # فحص إن الاستراتيجيات مش بتبص على المستقبل
scripts/freqai_run.sh --fresh   # FreqAI walk-forward (~4 دقايق على 4 أنوية)
```

تقسيم الوقت ثابت: **تطوير** 2022–2024، **اختبار (holdout)** من 1 يناير 2025 لـ 25 سبتمبر 2026.
فترة الاختبار اتشافت خلاص، فأي تعديل جديد على الاستراتيجيات محتاج فترة اختبار جديدة (مثلاً dry-run لايف).

### Dry-run لايف على Bybit (على جهازك أو VPS مش في أمريكا)

```bash
.venv/bin/freqtrade trade -c config/config.bybit.dryrun.json -s RsiMeanReversionBaseline
```

ده بيستخدم أسعار Bybit الحقيقية بمحفظة وهمية 100 USDT، ومش محتاج API key.
`config/config.freqai.json` مبني على إعدادات الباك تست (OKX)، فتشغيل FreqAI لايف على Bybit محتاج config خاص بيه (لسه ما اتعملش).

## ملاحظات

- البيانات من OKX كبديل لـ Bybit، لأن Bybit حاجب السيرفر اللي اتعمل عليه الشغل. على جهاز في مصر ينفع `EXCHANGE=bybit scripts/setup.sh` (ووقتها غيّر `exchange.name` في `config/config.backtest.json` لـ `bybit`).
- أقل أوردر Spot على Bybit عن طريق الـ API هو 5 USDT، فحساب فيه 2 دولار مش هيقدر يتداول حقيقي.
- مفاتيح الـ API ماتتحطش في الريبو. لو اتعمل تداول حقيقي بعدين: مفتاح من غير صلاحية سحب، مربوط بـ IP، على حساب فرعي.
