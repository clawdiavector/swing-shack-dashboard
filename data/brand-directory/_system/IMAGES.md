# Where images and logos live

One home for each kind of picture. If you are about to save an image somewhere
else, stop and use this table.

| What | Home | In git? | Who adds it |
|---|---|---|---|
| Our own photos (products, venue, services, video) | Each brand's Google Drive folder. Staff drop files in `Inbox`; the Photos page (Today > Photos) names and files them | No (Drive is the master; the app pulls a copy) | Staff, then Claude moves them |
| A brand's own logos | `data/brand-directory/<brand>/logos/`, listed in `logos/logos.json` | Yes | Christelle, from the designer's files |
| Makers' logos (Callaway, Vice, RIPIT, Takomo…) | `data/brand-directory/_shared/maker-logos/<maker>.png`, one set for every brand | Yes | The maker's own header logo, transparent PNG |
| Official maker images (catalogue / sourced) | `data/brand-directory/_shared/catalogue/`: `catalogue.json` says what each is and where it came from; the files are in `images/<maker>/` | Index yes, pictures no | The image scout (`image-scout` skill) |
| Where to find each maker's images, and whether we may use them | `data/brand-directory/_system/image-sources.json` (`rights` per maker) | Yes | Christelle records the OK |
| Template references, photos, golden renders | `data/brand-directory/<brand>/templates/<name>/` | Yes | `campaign-os-template` |

## Rules

- **One copy of a logo.** Templates point at `logos/…`; never copy a logo into a template's `assets/`.
- **Maker logos are shared.** File name = maker name in lower case with dashes (`L.A.B. Golf` → `lab-golf.png`).
- **Sourced images keep their source.** Every catalogue image records the maker's page and the image address. The same image for the second shop comes from the catalogue, not a second download.
- **Rights before use.** A sourced photo cannot be approved on the Photos page until its maker's `rights.status` in `image-sources.json` is `cleared` (`not-cleared` = never; `unknown` = nobody has checked). Write who gave the OK and when in `basis`.
- **Never generated, never a retailer's copy** of a product we sell (see `image-sources.json` rules).

## Not done yet

- The catalogue pictures live on the machine that ran the scout. They are not on Drive or live yet.
- Stick's templates still use a small 239×85 copy of the logo (`stick/logo.png`), marked `outdated` in `stick/logos/logos.json`.
- Stick still keeps copies of the maker logos in `stick/logos/vendors/` because an older test checks that folder. A test makes sure they match the shared ones.
