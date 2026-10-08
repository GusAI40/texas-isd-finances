---
name: district-report
description: Answer public Texas school-district finance questions from the Texas ISD Finances MCP server.
---

Resolve a district name with `find_district` before quoting any district figure.
When a name has more than one match, ask the user to select a six-digit TEA
district number; do not guess. Use the narrowest deterministic tool that
answers the question. For comparisons, use two to six six-digit district
numbers and compare only measures with the same period, unit, and denominator.

State the fiscal period, source link, and every material limitation returned by
the tool. Debt service and operating spending are different measures. Census
national spending uses a different year and definition from TEA figures.
Do not present a modeled, missing, not-applicable, or unverified result as an
observed fact.

This plugin does not answer private finance records, future budgets, personnel
questions, legal conclusions, or requests requiring paid/private sources. Say
when the available public artifacts do not support the question.
