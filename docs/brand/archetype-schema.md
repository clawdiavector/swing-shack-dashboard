# Archetype schema v2

Normative JSON Schema for `visual-spec/archetypes.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://campaign-os/brand-directory/visual-archetypes/v2",
  "type": "object",
  "required": [
    "schema",
    "brand_id",
    "version",
    "canvases",
    "archetypes"
  ],
  "properties": {
    "schema": {
      "const": "https://campaign-os/brand-directory/visual-archetypes/v2"
    },
    "brand_id": {
      "type": "string"
    },
    "version": {
      "type": "string"
    },
    "updated": {
      "type": "string",
      "format": "date-time"
    },
    "source": {
      "enum": [
        "measured",
        "draft",
        "best-guess"
      ]
    },
    "measured_from": {
      "type": "array",
      "description": "Brand-relative paths of the real assets the geometry was taken from. Required when source == measured.",
      "items": {
        "type": "string"
      }
    },
    "canvases": {
      "type": "object",
      "description": "Named output canvases. Keys are canvas ids referenced by archetype.canvas and canvas_overrides.",
      "additionalProperties": {
        "type": "object",
        "required": [
          "w",
          "h",
          "aspect",
          "channels"
        ],
        "properties": {
          "w": {
            "type": "integer",
            "minimum": 1
          },
          "h": {
            "type": "integer",
            "minimum": 1
          },
          "aspect": {
            "type": "string",
            "pattern": "^[0-9.]+:[0-9.]+$"
          },
          "channels": {
            "type": "array",
            "items": {
              "enum": [
                "instagram",
                "instagram_story",
                "facebook",
                "gbp",
                "tiktok",
                "twitter"
              ]
            }
          },
          "safe_zone": {
            "$ref": "#/$defs/rect"
          }
        }
      }
    },
    "archetypes": {
      "type": "array",
      "minItems": 1,
      "maxItems": 4,
      "items": {
        "type": "object",
        "required": [
          "id",
          "name",
          "canvas",
          "applies_to",
          "background",
          "zones",
          "logo_anchor"
        ],
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"
          },
          "name": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "canvas": {
            "type": "string",
            "description": "Key into canvases \u2014 the canvas the zones were measured on."
          },
          "block_anchor": {
            "enum": [
              "center",
              "top",
              "bottom"
            ],
            "default": "center",
            "description": "How the measured block is re-anchored when rendering to a taller/shorter canvas. center reproduces the post->story shift measured on Stick pairs A and B."
          },
          "canvas_overrides": {
            "type": "object",
            "description": "Per-canvas zone overrides for archetypes whose geometry is not a pure re-anchor (Stick pair C). Keys are canvas ids; values are partial zone maps.",
            "additionalProperties": {
              "type": "object",
              "additionalProperties": {
                "$ref": "#/$defs/zone"
              }
            }
          },
          "applies_to": {
            "type": "object",
            "required": [
              "channels"
            ],
            "properties": {
              "channels": {
                "type": "array",
                "minItems": 1,
                "items": {
                  "enum": [
                    "instagram",
                    "instagram_story",
                    "facebook",
                    "gbp",
                    "tiktok",
                    "twitter"
                  ]
                }
              },
              "pillars": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "record_types": {
                "type": "array",
                "items": {
                  "enum": [
                    "moment",
                    "campaign",
                    "evergreen"
                  ]
                }
              },
              "needs_photo": {
                "type": "boolean",
                "default": true,
                "description": "false = deterministic-only archetype; compose_post renders it with no draft_photo candidate and the moment skips the paid stage entirely."
              }
            }
          },
          "background": {
            "type": "object",
            "required": [
              "kind"
            ],
            "properties": {
              "kind": {
                "enum": [
                  "photo_full_bleed",
                  "photo_band",
                  "solid",
                  "gradient"
                ]
              },
              "fill": {
                "type": "string",
                "description": "Palette token or #hex. Required for solid."
              },
              "gradient": {
                "type": "object",
                "properties": {
                  "from": {
                    "type": "string"
                  },
                  "to": {
                    "type": "string"
                  },
                  "direction": {
                    "enum": [
                      "to-bottom",
                      "to-top",
                      "to-right",
                      "to-left"
                    ]
                  }
                }
              },
              "scrim": {
                "type": "object",
                "description": "Darkening applied over photo where text sits.",
                "properties": {
                  "rect": {
                    "$ref": "#/$defs/rect"
                  },
                  "from_alpha": {
                    "type": "number"
                  },
                  "to_alpha": {
                    "type": "number"
                  }
                }
              }
            }
          },
          "zones": {
            "type": "object",
            "description": "Zone id -> zone. Reserved ids: photo, headline, subhead, cta, logo, partner_logo, tagline, vendor_lockup, cta_band.",
            "additionalProperties": {
              "$ref": "#/$defs/zone"
            }
          },
          "logo_anchor": {
            "type": "object",
            "required": [
              "zone",
              "variant",
              "fit"
            ],
            "properties": {
              "zone": {
                "type": "string",
                "description": "Zone id the brand logo is drawn into."
              },
              "variant": {
                "enum": [
                  "mono_light",
                  "mono_dark",
                  "full_colour"
                ]
              },
              "fit": {
                "enum": [
                  "contain",
                  "height",
                  "width"
                ]
              },
              "align": {
                "enum": [
                  "left",
                  "center",
                  "right"
                ],
                "default": "left"
              }
            }
          },
          "safe_zone": {
            "$ref": "#/$defs/rect",
            "description": "No zone of kind text or logo may fall outside this rect. Zones of kind image or band may full-bleed past it by design \u2014 every measured Stick archetype does (photo bands to x 0.0-1.0, the service-frame CTA band to x 1.0). Defaults to the canvas safe_zone."
          },
          "max_total_chars": {
            "type": "integer",
            "description": "Hard cap across all text zones; compose_post falls back to a shorter archetype rather than shrinking type below min_font_px."
          }
        }
      }
    }
  },
  "$defs": {
    "rect": {
      "type": "object",
      "required": [
        "x0",
        "y0",
        "x1",
        "y1"
      ],
      "description": "Fractions of canvas width (x) and height (y), origin top-left.",
      "properties": {
        "x0": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "y0": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "x1": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "y1": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "zone": {
      "type": "object",
      "required": [
        "rect",
        "kind"
      ],
      "properties": {
        "rect": {
          "$ref": "#/$defs/rect"
        },
        "kind": {
          "enum": [
            "text",
            "image",
            "logo",
            "band",
            "decorative"
          ]
        },
        "source": {
          "enum": [
            "caption_hook",
            "caption_body",
            "cta",
            "product_name",
            "vendor_name",
            "brand_tagline",
            "static",
            "photo"
          ],
          "description": "Where compose_post gets the content. static means the literal in `text`."
        },
        "text": {
          "type": "string",
          "description": "Literal content when source == static."
        },
        "font_role": {
          "enum": [
            "display",
            "h1",
            "h2",
            "h3",
            "body",
            "caption",
            "cta"
          ],
          "description": "Key into typography/fonts.json scale. compose_post never hard-codes a px size."
        },
        "max_lines": {
          "type": "integer",
          "minimum": 1
        },
        "max_chars_per_line": {
          "type": "integer",
          "minimum": 1
        },
        "line_height": {
          "type": "number",
          "description": "Multiple of the rendered font size. Measured value, not a guess."
        },
        "align": {
          "enum": [
            "left",
            "center",
            "right"
          ],
          "default": "left"
        },
        "valign": {
          "enum": [
            "top",
            "middle",
            "bottom"
          ],
          "default": "top"
        },
        "colour": {
          "type": "string",
          "description": "Palette token or #hex."
        },
        "fill": {
          "type": "string",
          "description": "Band fill for kind == band."
        },
        "min_font_px": {
          "type": "integer",
          "description": "Below this, compose_post fails the zone rather than rendering unreadable type."
        },
        "optional": {
          "type": "boolean",
          "default": false,
          "description": "true = zone is dropped silently when its source yields nothing; false = missing content is a compose_post error."
        }
      }
    }
  }
}
```
