# Local model-eval transcripts

Drop pasted chat exports here as `.md` files. Git tracks only this
README and `.gitkeep`. Transcripts stay on this machine.

One file per conversation. Load the GGUF first. Sidebar **Reasoning
time** = `~6 min`. **New chat** for every conversation. Attach once,
copy the inventory turn into the file, then paste the questions below
in order.

## File names

```
<gguf-stem>__C1_S1-ginzu.md
<gguf-stem>__C2_F1-rates-books.md
<gguf-stem>__C3_S2-wacc.md
<gguf-stem>__C4_F2-wacc-ratings.md
<gguf-stem>__C5_F3-rates-only.md
```

Example: `Gemma-2-9b-it-Q4_K_M-fp16__C1_S1-ginzu.md`

## Downloads

Do **not** open https://pages.stern.nyu.edu/~adamodar/pc/ (directory
listing is 403 Forbidden). Use the catalog page or a **file** URL.
Catalog: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm
Damodaran notes Chrome often fails these downloads; use Edge if needed.
Do not use exinfm items 6, 30, or 41 (macros / exe).

| Id | How to attach | Direct file URL |
| --- | --- | --- |
| S1 | Paperclip, one file | https://pages.stern.nyu.edu/~adamodar/pc/fcffsimpleginzu.xlsx |
| S2 | Paperclip, one file | https://pages.stern.nyu.edu/~adamodar/pc/wacccalc.xls |
| S3 | Paperclip, one file | https://pages.stern.nyu.edu/~adamodar/pc/ratings.xls (C4 folder only) |
| F1 | Folder picker | `Books.xlsx` + `Rates.xlsx` (linked pack already used in tests) |
| F2 | Folder picker | `wacccalc.xls` + `ratings.xls` (two files, no link expected) |
| F3 | Folder picker | `Rates.xlsx` only (Books missing) |

## C1 — S1 ginzu (one file)

Attach `fcffsimpleginzu.xlsx`. Then:

1. `What does Valuation output!C9 do?`
2. `What does Input sheet!B35 do?`
3. `List the named ranges from the inventory.`
4. `Are there external workbook links in the inventory?`
5. `What does Valuation output!B999 do?`
6. `How is terminal value calculated? Quote only a formula that is in the inventory.`
7. `Suggest a paste-ready FCFF-from-EBIT formula only if the inventory shows that logic.`

## C2 — F1 Rates + Books (folder)

Attach the folder that contains both files. Then:

1. `What does Valuation output!C9 do?`
2. `What does Rates!E2 do?`
3. `Which file does Rates read, and is it in this pack?`
4. `List the named ranges from the inventory.`
5. `Are there external workbook links in the inventory?`
6. `How is the book name pulled into Rates? Quote only a formula that is in the inventory.`
7. `Suggest a paste-ready formula that looks up a name the same way Rates already does.`

## C3 — S2 WACC (one file)

Attach `wacccalc.xls`. Copy the inventory. For question 4, replace
`[Sheet]!A1` with a cell **listed in that inventory**. Then:

1. `List the named ranges from the inventory.`
2. `Are there external workbook links in the inventory?`
3. `Where is WACC or the cost of capital computed?`
4. `What does [Sheet]!A1 do?`
5. `What does Input!Z999 do?`
6. `How is the cost of capital calculated? Quote only a formula that is in the inventory.`
7. `Suggest a paste-ready WACC formula only if the inventory already shows that logic.`

## C4 — F2 wacc + ratings (folder)

Attach a folder that contains only `wacccalc.xls` and `ratings.xls`. Then:

1. (inventory turn — copy it; no extra question)
2. `Are there external workbook links in the inventory?`
3. `Which file does Rates read, and is it in this pack?`
4. `What does Rates!E2 do?`
5. `Where is WACC or the cost of capital computed?`
6. `How is the cost of capital calculated? Quote only a formula that is in the inventory.`

## C5 — F3 Rates only (folder)

Attach a folder that contains only `Rates.xlsx`. Then:

1. (inventory turn — copy it)
2. `Which file does Rates read, and is it in this pack?`
3. `What does Rates!E2 do?`
4. `Are there external workbook links in the inventory?`
5. `What does Books!B2 do?`
6. `How is the book name pulled into Rates? Quote only a formula that is in the inventory.`
