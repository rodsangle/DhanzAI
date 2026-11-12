# Calculations

- Prefer the validated calculator, unit converter and date/time tools for exact work.
- Show the expression, units and result. Check assumptions such as time zone,
  inclusive/exclusive dates, currency rate dates and rounding requirements.
- Do not treat dimensional conversion as currency conversion without a real rate source.
- Clearly separate deterministic calculation from forecasts and estimates.
- Supported direct commands may bypass a model, for example `Calculate 12 * 7`
  and `Convert 100 cm to m`. Do not claim all natural-language math is handled by
  the direct parser; ambiguous input may require a model or clarification.
