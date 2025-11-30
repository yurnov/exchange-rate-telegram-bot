# Changelog

## v0.7.0

3PP lifecycle:
- Python 3.14
- Dependency updated
- Dockerfile refactored to use requirements.txt for correct Dependabot action

## v0.6.0

[EUR<=>USD conversion support added](https://github.com/yurnov/exchange-rate-telegram-bot/pull/25)

## v0.5.0

New `/calc` command - Parses input like `/calc 100 USD` to UAH and returns converted amount with rate used [#22](https://github.com/yurnov/exchange-rate-telegram-bot/pull/22)

## v0.4.0

NBU rates added

## v0.3.0

[Optinal logging exchange rates to CSV file](https://github.com/yurnov/exchange-rate-telegram-bot/issues/4)
Log level for application log is configurable

## v0.2.1

Code is same as `v0.2.0`, just fix in README.md

## v0.2.0

Instead of individual API call for each `/rate` bot command rates pulled in configurable interval

## 0.1.1

Version with fix of `/start` answer

## 0.1.0 (yanked)

Version yanked due to code error

## [pre-0.1.0](c218c5c43a8d3a3c477740b424e7d8ea53e487cf)

First working version