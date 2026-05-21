# Campaign OS — Swing Shack

Operational marketing application for Swing Shack's indoor golf content pipeline.

## Architecture

**Client-side only. No backend. State lives in localStorage.**

- `campaign-data.json` — Seed data for all campaigns, assets, approvals, shoots, stats, and activity
- `app.js` — Core application logic (state management, rendering, mutations)
- `command-centre.html` — Main dashboard (campaign overview, stats, approvals, activity)
- `workspace-*.html` — Per-campaign workspace (pipeline, collateral, schedule)

## How It Works

1. **Init**: `CampaignOS.init()` loads `campaign-data.json` into localStorage on first visit
2. **State**: All mutations hit localStorage via `saveState()` — survives page reloads
3. **Rendering**: `renderCommandCentre()` and `renderWorkspace(campaignId)` overwrite HTML content with live data from state
4. **Navigation**: `openCampaign(id)` navigates to `workspace-trackman.html?campaign=<id>`
5. **URL**: `getCampaignFromURL()` reads `?campaign=` param to load correct campaign

## Key Functions

```javascript
CampaignOS.init()                      // Init + load seed
CampaignOS.getState()                  // Get current localStorage state
CampaignOS.saveState(state)            // Persist state
CampaignOS.resetState()                // Reset to seed data

// Campaign actions
CampaignOS.approveAsset(cid, aid)      // READY → SCHEDULED
CampaignOS.rejectAsset(cid, aid)       // → LEARNING
CampaignOS.scheduleAsset(cid, aid, date, time)  // → LIVE
CampaignOS.publishAsset(cid, aid)      // → LIVE
CampaignOS.archiveAsset(cid, aid)     // → LEARNING
CampaignOS.moveAssetToStage(cid, aid, stage)  // arbitrary move

// Approval actions
CampaignOS.approveItem(approvalId)      // approves + removes from queue
CampaignOS.rejectItem(approvalId)       // removes from queue

// Navigation
CampaignOS.openCampaign(campaignId)    // navigate to workspace
CampaignOS.getCampaignFromURL()        // read ?campaign= param

// Rendering
CampaignOS.renderCommandCentre()       // render main dashboard
CampaignOS.renderWorkspace(campaignId) // render campaign workspace
CampaignOS.renderPipeline(campaignId)  // render 7-stage pipeline
CampaignOS.renderCollateral(campaignId)// render collateral gallery

// Activity
CampaignOS.logActivity(type, message)  // add to activity feed

// Detail modal
showAssetDetail(campaignId, assetId)    // opens asset detail modal
```

## Deployment

Deploy to GitHub Pages. All paths are relative.

Media assets: `../../media/generated/...` (resolved from `/campaign-os/`)

## Development

```bash
# View locally (any static server)
python3 -m http.server 8080
# then open http://localhost:8080/campaign-os/command-centre.html

# Reset state (clear localStorage and re-seed)
# → open DevTools → Application → Local Storage → Clear
# → refresh
```