# طريقة الشغل الثابتة (Workflow)

أي طلب شغل في الريبو ده يمشي بالترتيب ده. ماينفعش نبدأ تنفيذ مباشر من غير ما نعدي على الخطوات اللي قبله.

1. **أدوات البحث:** ندور على الإنترنت على Skills أو MCP servers تساعد في البحث والتنفيذ للمهمة دي، ونوصّل اللي ينفع منها.
2. **البحث:** نبحث بحث حقيقي بمصادر أصلية. لو فيه ريسيرش موجود، نشوف الأول هو كفاية ولا فيه ثغرات، ونكمّل الناقص بس.
3. **الخطة:** نرتب الشغل وننظمه ونقسمه لمهام واضحة، كل مهمة ليها مخرج محدد وطريقة تتأكد بيها إنها اتعملت صح.
4. **التوزيع على Agents:** كل مهمة تروح لـ agent مسؤول عنها يشتغلها كاملة.
5. **المراجعة:** نراجع شغل كل agent ونجرّبه فعلياً (نشغّل الكود والتستات)، ونصلّح اللي فيه مشكلة قبل ما نسلّم.
6. **التسليم:** نسلّم منتج كامل شغال، مش أجزاء متفرقة، مع شرح مختصر هو بيعمل إيه وإزاي يتشغل.

---

# About the project

The goal is an AI-assisted crypto trading bot, built on Freqtrade/FreqAI and targeting Bybit.
The starting research lives in the conversation (AI_Trading_Research_AR_2026-09-26).

Hard rules:
- Dry-run / paper trading first. Real money only after backtest + dry-run results justify it, and only with the owner's explicit approval.
- API keys and passwords never go in the repo or the chat. Real trading uses a key without withdrawal permission, stored on the machine that runs the bot.
- Every result is reported after all costs (fees, slippage, funding), compared against buy-and-hold and holding cash, and checked for look-ahead bias.
- Never promise returns.
