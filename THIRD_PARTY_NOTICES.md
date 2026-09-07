# Third-party notices

The MIT License in this repository covers only the independently authored
AAsource software. It does not license third-party market data, service
endpoints, trademarks, protocols, or content.

## Runtime dependencies

| Dependency | Version range | License / status | Upstream |
|---|---|---|---|
| pandas | `>=2.2,<3` | BSD-3-Clause | https://github.com/pandas-dev/pandas |
| Requests | `>=2.31,<3` | Apache-2.0 | https://github.com/psf/requests |
| PyYAML | `>=6,<7` | MIT | https://github.com/yaml/pyyaml |
| pytdx | `==1.72` | No standard license declared; upstream states personal research/non-commercial use | https://github.com/rainx/pytdx |

`pytdx` is installed as an external dependency and is not bundled in this
repository or wheel. Users must review and comply with its upstream terms.

## Bundled files

| File | Origin | Status |
|---|---|---|
| `src/aasource/providers/vendor/ths.js` | Obfuscated browser script served by 同花顺 (10jqka); redistributed in the AKShare project (MIT) at `akshare/data/ths.js` | Included solely to compute the `v` (hexin-v) cookie required by `q.10jqka.com.cn` pages. It remains 同花顺's non-free content: it is not licensed under this repository's MIT License and is used at the user's own responsibility. |

## Optional dependencies

| Dependency | Used by | License | Upstream |
|---|---|---|---|
| py_mini_racer | `sectors list --kind ths_concept` (THS `v` cookie generation) | Apache-2.0 | https://github.com/sqreen/PyMiniRacer |

## Data providers

This project is not affiliated with or endorsed by TongdaXin, Tencent,
Eastmoney, 同花顺 (THS / 10jqka), 乐咕乐股 (legulegu.com), 申万宏源研究 (SWS
Research), any securities exchange, or any market-data vendor. Shenwan
industry classification is a methodology owned by SWS Research; the
legulegu.com pages used here are third-party renditions of it. Provider data
and endpoints are not covered by this project's MIT License. Users are
responsible for determining whether their access, caching, processing, and use
of provider data comply with all applicable terms and laws.
