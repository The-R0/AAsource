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

## Data providers

This project is not affiliated with or endorsed by TongdaXin, Tencent,
Eastmoney, any securities exchange, or any market-data vendor. Provider data
and endpoints are not covered by this project's MIT License. Users are
responsible for determining whether their access, caching, processing, and use
of provider data comply with all applicable terms and laws.
