# Sources and design choices

These are primary documentation and original research papers consulted for the
starter's boundaries. None supplies fixture data or proves this lab can predict
returns.

| Source | What it informs here |
| --- | --- |
| [Alpaca, Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading) | Paper execution differs from live execution; the docs list omitted effects including market impact, latency slippage, queue position, fees, and dividends. This starter does **not** call Alpaca, and its local invented-price ledger is simpler still. |
| [Alpaca, About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api) | Real-time and historical feeds have plan-specific coverage and conditions. No API, feed, credentials, or data from Alpaca are used here. Access and permitted uses need a separate review before any integration. |
| [QuantConnect, Research Engine](https://www.quantconnect.com/docs/v2/research-environment/key-concepts/research-engine) | Research is a distinct activity from event-driven execution. Our worker boundary produces a memo, never an order. |
| [QuantConnect, Live Trading Reconciliation](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) | Custom data's *availability* can lag its event timestamp, and look-ahead bias can persist. Fixtures record both observed/published time and available time; memos reject future evidence and only select available prices. |
| [QuantConnect, Slippage Models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models) and [Fee Models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/supported-models) | Costs and fill assumptions affect results. Our 0.10% per-side slippage and $1 per-side fee are *chosen examples*, not fitted models or broker terms. |
| [FINRA, Regulatory Notice 15-09](https://www.finra.org/rules-guidance/notices/15-09) | Describes supervision, testing, validation, trading-system, and compliance controls for algorithmic strategies. It is guidance for relevant market participants, not a certification or a live-trading checklist fulfilled by this lab. |
| [FRED Services Terms of Use](https://fred.stlouisfed.org/legal/#fred-terms) | Some series have third-party rights and restrictions. Do not bundle FRED data, scrape it, or presume redistribution or AI-processing rights from the MIT license on this code. |
| [TradingAgents, original paper](https://arxiv.org/html/2412.20138) | Specialized perspectives and structured handoffs motivated the context/catalyst/skeptic split. This starter does not implement the paper's LLM system or its trading claims. |
| [FinMem, original paper](https://arxiv.org/html/2311.13743) | A retrospective record can help revisit previous evidence. This starter stores a simple price observation and the original cited countercase, not FinMem's memory model. |

Research papers are ideas to interrogate, not evidence that a trading system is
profitable. A future evaluation needs licensed data, point-in-time availability,
out-of-sample controls, realistic costs, and clear human review before its
results mean anything.
