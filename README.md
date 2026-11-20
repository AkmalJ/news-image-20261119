# The World in One Day — Thursday 19 November 2026

A one-page broadsheet that sums up the world news of **Thursday 19 November
2026** in a single 1024×1024 image: 35 dated stories — three wide features
(the first Trump–Xi–Putin summit in Shenzhen, the World Court's Myanmar
genocide verdict, and the COP31 draft deal), ten illustrated medium stories,
the day in numbers, a dotted world map with numbered pins, and 22 further
one-sentence briefs, each attributed to its source.

This is an entry for make.fun's **news-image-20261119** bounty,
"Sum up 19 November's world news in one image".

## How it is made

Every element of the page — masthead, feature art, map, charts — is drawn in
code with Pillow. No photograph or external asset is used. The page is
rendered at 2048×2048 and downscaled to 1024×1024 (Lanczos) so the small
type stays crisp. The render is deterministic: re-running the generator
reproduces a byte-identical `entry.png`.

## Run it

```sh
python3 generate.py          # draws the page, writes entry.png
node main.ts                 # validates entry.png and copies it to /output
OUTPUT_DIR=./out node main.ts   # ...or to a directory of your choice
```

`main.ts` checks that `entry.png` exists and is within the competition's
1 MiB limit, prints its SHA-256, and copies it byte-for-byte to
`<OUTPUT_DIR>/entry.png` (`OUTPUT_DIR` defaults to `/output`).

## Files

- `generate.py` — the page generator (Python 3 + Pillow, DejaVu fonts).
- `entry.png` — the generated front page, 1024×1024.
- `main.ts` — the entry program (Node.js, standard library only).
- `SOURCES.md` — every story on the page with its source.
- `LICENSE` — MIT.

Claims on the page are attributed, not stated as fact. Stories were chosen
only if they happened, or were first reported, on Thursday 19 November 2026;
the page's DATE CHECK box lists the near-miss stories left out as other
days' news.
