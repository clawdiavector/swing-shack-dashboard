/**
 * CampaignOS — Swing Shack Campaign Operating System
 * Client-side only. State lives in localStorage, seeded from campaign-data.json
 */
(function() {
  'use strict';

  var CampaignOS = window.CampaignOS = {};

  var STORAGE_KEY = 'swing_shack_campaign_os';
  var SEED_FILE = 'campaign-data.json';

  // ─── STATE MANAGEMENT ────────────────────────────────────────────────

  CampaignOS.init = function() {
    return new Promise(function(resolve) {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        resolve();
      } else {
        fetch(SEED_FILE)
          .then(function(r) { return r.json(); })
          .then(function(seed) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(seed));
            resolve();
          })
          .catch(function() {
            // Fallback: empty state
            localStorage.setItem(STORAGE_KEY, JSON.stringify({ campaigns: [], approvals: [], shoots: [], stats: {}, activity: [] }));
            resolve();
          });
      }
    });
  };

  CampaignOS.getState = function() {
    var raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  };

  CampaignOS.saveState = function(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  CampaignOS.resetState = function() {
    var self = this;
    fetch(SEED_FILE)
      .then(function(r) { return r.json(); })
      .then(function(seed) {
        self.saveState(seed);
      });
  };

  CampaignOS._mutate = function(fn) {
    var state = this.getState();
    fn(state);
    this.saveState(state);
  };

  // ─── CAMPAIGN ACTIONS ────────────────────────────────────────────────

  CampaignOS.approveAsset = function(campaignId, assetId) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      asset.stage = 'SCHEDULED';
      asset.status = 'scheduled';
      // Remove from all pipeline slots
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.SCHEDULED = campaign.pipelineAssets.SCHEDULED || [];
      campaign.pipelineAssets.SCHEDULED.push(assetId);
      // Remove from approvals
      state.approvals = state.approvals.filter(function(a) { return a.assetId !== assetId; });
      this.logActivity('approved', asset.title + ' approved and scheduled');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.rejectAsset = function(campaignId, assetId) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      asset.stage = 'LEARNING';
      asset.status = 'archived';
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.LEARNING = campaign.pipelineAssets.LEARNING || [];
      campaign.pipelineAssets.LEARNING.push(assetId);
      state.approvals = state.approvals.filter(function(a) { return a.assetId !== assetId; });
      this.logActivity('rejected', asset.title + ' rejected');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.scheduleAsset = function(campaignId, assetId, date, time) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      var dt = date + 'T' + (time || '12:00') + ':00+02:00';
      asset.scheduledTime = dt;
      asset.scheduledDate = date;
      asset.stage = 'LIVE';
      asset.status = 'live';
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.LIVE = campaign.pipelineAssets.LIVE || [];
      campaign.pipelineAssets.LIVE.push(assetId);
      this.logActivity('scheduled', asset.title + ' posted live on ' + date);
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.publishAsset = function(campaignId, assetId) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      asset.stage = 'LIVE';
      asset.status = 'live';
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.LIVE = campaign.pipelineAssets.LIVE || [];
      campaign.pipelineAssets.LIVE.push(assetId);
      this.logActivity('live', asset.title + ' is now live');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.archiveAsset = function(campaignId, assetId) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      asset.stage = 'LEARNING';
      asset.status = 'archived';
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.LEARNING = campaign.pipelineAssets.LEARNING || [];
      campaign.pipelineAssets.LEARNING.push(assetId);
      this.logActivity('learning', asset.title + ' moved to Learning');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.moveAssetToStage = function(campaignId, assetId, stage) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === assetId; });
      if (!asset) return;
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets[stage] = campaign.pipelineAssets[stage] || [];
      campaign.pipelineAssets[stage].push(assetId);
      asset.stage = stage;
    });
    this.refreshUI();
  };

  CampaignOS.addAsset = function(campaignId, asset) {
    this._mutate(function(state) {
      var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
      if (!campaign) return;
      campaign.assets.push(asset);
      campaign.pipelineAssets[asset.stage] = campaign.pipelineAssets[asset.stage] || [];
      campaign.pipelineAssets[asset.stage].push(asset.id);
    });
    this.refreshUI();
  };

  // ─── APPROVAL ACTIONS ────────────────────────────────────────────────

  CampaignOS.approveItem = function(approvalId) {
    this._mutate(function(state) {
      var item = state.approvals.find(function(a) { return a.id === approvalId; });
      if (!item) return;
      var campaign = state.campaigns.find(function(c) { return c.id === item.campaign; });
      if (!campaign) return;
      var asset = campaign.assets.find(function(a) { return a.id === item.assetId; });
      if (!asset) return;
      asset.stage = 'READY';
      asset.status = 'ready';
      campaign.pipelineOrder.forEach(function(s) {
        var idx = campaign.pipelineAssets[s].indexOf(item.assetId);
        if (idx > -1) campaign.pipelineAssets[s].splice(idx, 1);
      });
      campaign.pipelineAssets.READ = campaign.pipelineAssets.READ || [];
      campaign.pipelineAssets.READ.push(item.assetId);
      state.approvals = state.approvals.filter(function(a) { return a.id !== approvalId; });
      this.logActivity('approved', asset.title + ' approved');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.rejectItem = function(approvalId) {
    this._mutate(function(state) {
      var item = state.approvals.find(function(a) { return a.id === approvalId; });
      if (!item) return;
      var asset;
      var campaign = state.campaigns.find(function(c) { return c.id === item.campaign; });
      if (campaign) asset = campaign.assets.find(function(a) { return a.id === item.assetId; });
      state.approvals = state.approvals.filter(function(a) { return a.id !== approvalId; });
      this.logActivity('rejected', (asset ? asset.title : 'Item') + ' rejected and removed');
    }.bind(this));
    this.refreshUI();
  };

  CampaignOS.getApprovals = function() {
    return this.getState().approvals || [];
  };

  // ─── NAVIGATION ──────────────────────────────────────────────────────

  CampaignOS.openCampaign = function(campaignId) {
    window.location.href = 'workspace-trackman.html?campaign=' + campaignId;
  };

  CampaignOS.getCampaignFromURL = function() {
    var params = new URLSearchParams(window.location.search);
    return params.get('campaign') || 'trackman';
  };

  // ─── ACTIVITY FEED ──────────────────────────────────────────────────

  CampaignOS.logActivity = function(type, message) {
    this._mutate(function(state) {
      var entry = {
        id: 'act-' + Date.now(),
        type: type,
        message: message,
        time: new Date().toISOString()
      };
      state.activity = [entry].concat(state.activity || []).slice(0, 50);
    });
  };

  // ─── RENDERING ───────────────────────────────────────────────────────

  CampaignOS.refreshUI = function() {
    var path = window.location.pathname;
    if (path.indexOf('workspace-trackman') > -1 || path.indexOf('workspace-') > -1) {
      var cid = this.getCampaignFromURL();
      this.renderWorkspace(cid);
    } else {
      this.renderCommandCentre();
    }
  };

  CampaignOS.renderCommandCentre = function() {
    var state = this.getState();
    var campaigns = state.campaigns || [];
    var approvals = state.approvals || [];
    var shoots = state.shoots || [];
    var stats = state.stats || {};
    var activity = state.activity || [];

    // ── Health row ──
    var healthRow = document.querySelector('.health-row');
    if (healthRow) {
      var pills = '';
      var gradientMap = {
        'gradient-orange': '#1a2a3a',
        'gradient-blue': '#1a2a2a',
        'gradient-cold': '#1a2a2a',
        'gradient-green': '#1a2a1a',
        'gradient-purple': '#2a1a2a'
      };
      var dotMap = { healthy: 'green', attention: 'yellow', blocked: 'red' };
      campaigns.forEach(function(c) {
        var dot = dotMap[c.health] || 'green';
        pills += '<div class="health-pill" data-campaign-id="' + c.id + '" style="cursor:pointer"><div class="health-dot ' + dot + '"></div>' + c.name + '</div>';
      });
      healthRow.innerHTML = pills;
      healthRow.querySelectorAll('.health-pill').forEach(function(pill) {
        pill.addEventListener('click', function() {
          var id = pill.getAttribute('data-campaign-id');
          if (id) CampaignOS.openCampaign(id);
        });
      });
    }

    // ── Campaign grid ──
    var campaignGrid = document.querySelector('.campaign-grid');
    if (campaignGrid) {
      var self = this;
      var html = '';
      var gradClasses = ['grad-a','grad-b','grad-c','grad-d','grad-e','grad-a','grad-b','grad-c'];
      campaigns.forEach(function(c, i) {
        var dotMap2 = { healthy: 'green', attention: 'yellow', blocked: 'red' };
        var dot = dotMap2[c.health] || 'green';
        var badgeClass = c.health === 'healthy' ? 'healthy' : c.health === 'attention' ? 'attention' : 'blocked';
        var momentumArrow = c.momentum === 'up' ? '↑' : c.momentum === 'down' ? '↓' : '→';
        var momentumClass = c.momentum === 'up' ? 'up' : c.momentum === 'down' ? 'down' : 'neutral';
        var momentumPct = c.momentum === 'up' ? ' +' + (Math.floor(Math.random()*20)+5) + '%' :
                          c.momentum === 'down' ? ' -' + (Math.floor(Math.random()*15)+2) + '%' : ' 0%';
        var assetCount = c.assets ? c.assets.length : 0;
        var liveCount = c.assets ? c.assets.filter(function(a) { return a.stage === 'LIVE'; }).length : 0;
        var grad = gradClasses[i % gradClasses.length];
        var updatedAgo = self._timeAgo(c.lastUpdated);
        var btnLabel = 'REVIEW';
        if (c.status === 'planning') btnLabel = 'PLAN';
        if (c.status === 'scheduled') btnLabel = 'SCHEDULE';
        if (c.status === 'conversion') btnLabel = 'CONVERT';
        html +=
          '<div class="campaign-card" data-campaign-id="' + c.id + '">' +
            '<div class="card-visual ' + grad + '">' +
              '<div class="card-visual-overlay"></div>' +
              '<div class="card-status-badge ' + badgeClass + '">' +
                '<div class="health-dot ' + dot + '" style="width:5px;height:5px"></div>' +
                c.health.toUpperCase() +
              '</div>' +
              '<div class="card-health-dots">' +
                '<div class="dot ' + (c.health === 'healthy' ? 'lit-green' : 'off') + '"></div>' +
                '<div class="dot ' + (c.health === 'attention' ? 'lit-yellow' : 'off') + '"></div>' +
                '<div class="dot ' + (c.health === 'blocked' ? 'lit-red' : 'off') + '"></div>' +
              '</div>' +
            '</div>' +
            '<div class="card-body">' +
              '<div class="card-name">' + c.name + '</div>' +
              '<div class="card-meta"><span>📷 ' + assetCount + ' Assets</span><span>🎯 ' + liveCount + ' Live</span></div>' +
              '<div class="card-next-action">' +
                '<div>' +
                  '<div class="next-action-label">Next Action</div>' +
                  '<div class="next-action-text">' + (c.nextAction || '—') + '</div>' +
                '</div>' +
                '<button class="btn-cta">' + btnLabel + '</button>' +
              '</div>' +
              '<div class="card-footer">' +
                '<div class="card-updated">Updated ' + updatedAgo + '</div>' +
                '<div class="momentum ' + momentumClass + '"><span class="momentum-arrow">' + momentumArrow + '</span>' + momentumPct + '</div>' +
              '</div>' +
            '</div>' +
          '</div>';
      });
      campaignGrid.innerHTML = html;

      // Re-attach click handlers
      campaignGrid.querySelectorAll('.campaign-card').forEach(function(card) {
        card.addEventListener('click', function() {
          var id = card.getAttribute('data-campaign-id');
          if (id) CampaignOS.openCampaign(id);
        });
        card.style.cursor = 'pointer';
      });
    }

    // ── Stats ──
    this.renderStats();

    // ── Shoots ──
    var shootsList = document.querySelector('.shoots-list');
    if (shootsList) {
      var self = this;
      var html = '';
      shoots.forEach(function(s) {
        var parts = s.date.split('-');
        var day = parseInt(parts[2], 10);
        var mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(parts[1], 10) - 1];
        html +=
          '<div class="shoot-card">' +
            '<div class="shoot-date-block">' +
              '<div class="shoot-date-day">' + day + '</div>' +
              '<div class="shoot-date-mon">' + mon + '</div>' +
            '</div>' +
            '<div class="shoot-info">' +
              '<div class="shoot-name">' + s.campaign + ' — ' + s.type + '</div>' +
              '<div class="shoot-meta"><span>' + s.resources + '</span></div>' +
            '</div>' +
            '<div class="shoot-countdown">' +
              '<div class="countdown-num">' + s.countdown + '</div>' +
              '<div class="countdown-label">days</div>' +
            '</div>' +
          '</div>';
      });
      shootsList.innerHTML = html;
    }

    // ── Approvals ──
    var approvalsContainer = document.querySelector('.approvals-header') ? document.querySelector('.approvals-header').parentElement : null;
    if (approvalsContainer) {
      var headerEl = approvalsContainer.querySelector('.approvals-header');
      var badge = headerEl ? headerEl.querySelector('.count-badge') : null;
      if (badge) badge.textContent = approvals.length;
      var existingItems = approvalsContainer.querySelectorAll('.approval-item');
      existingItems.forEach(function(el) { el.remove(); });
      var self = this;
      approvals.forEach(function(a) {
        var timeAgo = self._timeAgo(a.submittedAt);
        var html =
          '<div class="approval-item" data-approval-id="' + a.id + '">' +
            '<div class="approval-thumb" style="background:linear-gradient(135deg,#1a2a3a,#0d1a26)"></div>' +
            '<div class="approval-info">' +
              '<div class="approval-campaign">' + a.campaign + '</div>' +
              '<div class="approval-type">' +
                '<span class="type-chip ' + a.type + '">' + a.type.charAt(0).toUpperCase() + a.type.slice(1) + '</span>' +
                a.title +
              '</div>' +
              '<div class="approval-time">' + timeAgo + '</div>' +
            '</div>' +
            '<button class="btn-approve" data-approve-id="' + a.id + '">✓</button>' +
          '</div>';
        var dummy = document.createElement('div');
        dummy.innerHTML = html;
        var item = dummy.firstElementChild;
        approvalsContainer.insertBefore(item, headerEl.nextSibling);
        item.querySelector('.btn-approve').addEventListener('click', function(e) {
          e.stopPropagation();
          self.approveItem(a.id);
        });
      });
    }

    // ── Activity feed ──
    var activityFeed = document.querySelector('.activity-feed');
    if (activityFeed) {
      var self = this;
      var html = '';
      activity.slice(0, 10).forEach(function(a) {
        var iconMap = { approved: '✓', scheduled: '⏱', created: '✦', paused: '⏸', rejected: '✗', learning: '◈', live: '▶' };
        var iconClass = a.type;
        html +=
          '<div class="activity-item">' +
            '<div class="activity-icon ' + iconClass + '">' + (iconMap[a.type] || '•') + '</div>' +
            '<div class="activity-text">' +
              '<div class="activity-main">' + a.message + '</div>' +
              '<div class="activity-time">' + self._timeAgo(a.time) + '</div>' +
            '</div>' +
          '</div>';
      });
      activityFeed.innerHTML = html;
    }
  };

  CampaignOS.renderStats = function() {
    var stats = this.getState().stats || {};
    var statCards = document.querySelectorAll('.stat-card');
    statCards.forEach(function(card) {
      var val = card.querySelector('.stat-value');
      if (!val) return;
      var target = parseFloat(val.dataset.target);
      var suffix = val.dataset.suffix || '';
      if (isNaN(target)) return;
      var isFloat = target % 1 !== 0;
      // Count-up
      var duration = 1400;
      var start = performance.now();
      function step(now) {
        var p = Math.min((now - start) / duration, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        var v = target * eased;
        val.textContent = (isFloat ? v.toFixed(1) : Math.floor(v).toLocaleString()) + suffix;
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);

      // Delta
      var delta = card.querySelector('.stat-delta');
      if (delta) {
        var key = val.dataset.target;
        if (key === '284700') delta.innerHTML = '↑ +' + stats.reachDelta + '% this week';
        if (key === '24') delta.innerHTML = '↑ +' + stats.postsDelta + ' new today';
        if (key === '6.8') delta.innerHTML = (stats.engagementDelta >= 0 ? '↑ +' : '↓ ') + stats.engagementDelta.toFixed(1) + '% vs last wk';
        if (key === '147') delta.innerHTML = '↑ +' + stats.bookingsDelta + ' this week';
      }
    });
  };

  CampaignOS.renderWorkspace = function(campaignId) {
    var state = this.getState();
    var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
    if (!campaign) return;
    var self = this;

    // Update breadcrumb
    var breadcrumb = document.querySelector('.breadcrumb .current');
    if (breadcrumb) breadcrumb.textContent = campaign.name;

    // Update badges
    var statusBadge = document.querySelector('.badge.scheduled, .badge.healthy, .badge.planning');
    if (statusBadge) {
      var cls = campaign.status === 'healthy' || campaign.status === 'conversion' ? 'healthy' : campaign.status === 'planning' ? 'planning' : 'scheduled';
      statusBadge.className = 'badge ' + cls;
      statusBadge.innerHTML = '<div class="dot"></div> ' + campaign.status.toUpperCase();
    }
    var tagline = document.querySelector('.tagline');
    if (tagline) tagline.textContent = campaign.tagline;

    // Update pipeline
    this.renderPipeline(campaignId);

    // Update collateral gallery
    this.renderCollateral(campaignId);
  };

  CampaignOS.renderPipeline = function(campaignId) {
    var state = this.getState();
    var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
    if (!campaign) return;

    var stagesEl = document.querySelector('.pipeline-stages');
    if (!stagesEl) return;

    var dotMap = {
      'PLANNING': 'orange',
      'SHOOTING': 'yellow',
      'EDITING': 'yellow',
      'READY': 'green',
      'SCHEDULED': 'green',
      'LIVE': 'green',
      'LEARNING': 'green'
    };

    var html = '';
    var stages = campaign.pipelineOrder || [];

    stages.forEach(function(stage, i) {
      var assets = (campaign.pipelineAssets[stage] || []).map(function(assetId) {
        var asset = campaign.assets.find(function(a) { return a.id === assetId; });
        if (!asset) return '';
        var dot = dotMap[stage] || 'green';
        return '<div class="asset-chip" data-asset-id="' + asset.id + '" data-campaign-id="' + campaign.id + '" style="cursor:pointer">' +
          '<div class="chip-dot ' + dot + '"></div>' +
          '<div class="chip-type">' + (asset.type ? asset.type.charAt(0).toUpperCase() + asset.type.slice(1) : 'Asset') + '</div>' +
          '<div class="chip-name">' + asset.title + '</div>' +
        '</div>';
      }).join('');

      if (assets === '') {
        assets = '<div style="display:flex;align-items:center;justify-content:center;height:60px;color:var(--text-dim);font-size:11px">No assets</div>';
      }

      var isActive = stage === 'SHOOTING';
      var count = (campaign.pipelineAssets[stage] || []).length;
      var assetWord = count === 1 ? 'asset' : 'assets';

      html +=
        '<div class="stage-col">' +
          '<div class="stage-header' + (isActive ? ' active' : '') + '">' +
            (isActive ? '<div class="stage-active-pulse"></div>' : '') +
            '<div class="stage-name' + (isActive ? ' active' : '') + '">' + stage.charAt(0) + stage.slice(1).toLowerCase() + '</div>' +
            '<div class="stage-count">' + count + '</div>' +
            '<div class="stage-count-label">' + assetWord + '</div>' +
          '</div>' +
          '<div class="stage-body' + (isActive ? ' active' : '') + '">' +
            assets +
          '</div>' +
        '</div>';

      if (i < stages.length - 1) {
        html += '<div class="pipeline-connector"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg></div>';
      }
    });

    stagesEl.innerHTML = html;

    // Re-attach pipeline chip click handlers
    var self = this;
    stagesEl.querySelectorAll('.asset-chip').forEach(function(chip) {
      chip.addEventListener('click', function() {
        var aid = chip.getAttribute('data-asset-id');
        var cid = chip.getAttribute('data-campaign-id');
        if (aid && cid) showAssetDetail(cid, aid);
      });
    });

    // Update pipeline meta
    var meta = document.querySelector('.pipeline-meta');
    if (meta) {
      var total = campaign.assets ? campaign.assets.length : 0;
      meta.textContent = total + ' assets across ' + stages.length + ' stages';
    }
  };

  CampaignOS.renderCollateral = function(campaignId) {
    var state = this.getState();
    var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
    if (!campaign || !campaign.assets) return;

    var galleryGrid = document.querySelector('.gallery-grid');
    if (!galleryGrid) return;

    var gradMap = ['grad-a','grad-b','grad-c','grad-d','grad-e'];

    var html = '';
    campaign.assets.forEach(function(asset, i) {
      var labelLower = asset.label ? asset.label.toLowerCase() : 'generated';
      var statusLabel = asset.status === 'ready' ? 'Ready to Post' :
                       asset.status === 'scheduled' ? 'Scheduled' :
                       asset.status === 'live' ? 'Live Now' :
                       asset.status === 'planning' ? 'In Planning' :
                       'Awaiting Approval';
      var statusClass = asset.status === 'ready' || asset.status === 'live' ? 'ready' : 'approval';
      var grad = gradMap[i % gradMap.length];
      var btnLabel = asset.status === 'ready' || asset.status === 'scheduled' ? 'Schedule' :
                     asset.status === 'live' ? 'Live' : 'Approve';
      var btnStyle = asset.status === 'live' ? 'background:var(--green);box-shadow:0 0 12px var(--green-glow)' : '';

      html +=
        '<div class="collateral-card" data-asset-id="' + asset.id + '">' +
          '<div class="collateral-visual ' + grad + '">' +
            '<div class="collateral-overlay"></div>' +
            '<div class="collateral-label ' + labelLower + '">' + (asset.label || 'Generated') + '</div>' +
            '<div class="collateral-status ' + statusClass + '">' + statusLabel + '</div>' +
            '<div class="collateral-hook">"' + asset.hook + '"</div>' +
          '</div>' +
          '<div class="collateral-body">' +
            '<div class="collateral-caption">' + asset.caption.replace(/\n/g, ' ') + '</div>' +
            '<div class="collateral-actions">' +
              '<button class="btn-action primary collateral-action-btn" data-action="schedule" data-asset-id="' + asset.id + '" data-campaign-id="' + campaign.id + '" style="' + btnStyle + '">' + btnLabel + '</button>' +
              '<button class="btn-action secondary collateral-action-btn" data-action="detail" data-asset-id="' + asset.id + '" data-campaign-id="' + campaign.id + '">Detail</button>' +
            '</div>' +
          '</div>' +
        '</div>';
    });

    galleryGrid.innerHTML = html;

    // Attach button handlers
    var self = this;
    galleryGrid.querySelectorAll('.collateral-action-btn').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var action = btn.getAttribute('data-action');
        var aid = btn.getAttribute('data-asset-id');
        var cid = btn.getAttribute('data-campaign-id');
        if (action === 'schedule') {
          var today = new Date();
          var dd = String(today.getDate() + 1).padStart(2, '0');
          var mm = String(today.getMonth() + 1).padStart(2, '0');
          var yyyy = today.getFullYear();
          var nextDate = yyyy + '-' + mm + '-' + dd;
          self.scheduleAsset(cid, aid, nextDate, '12:00');
        } else if (action === 'detail') {
          showAssetDetail(cid, aid);
        }
      });
    });

    // Click on card body also opens detail
    galleryGrid.querySelectorAll('.collateral-card').forEach(function(card) {
      card.addEventListener('click', function() {
        var aid = card.getAttribute('data-asset-id');
        if (aid) showAssetDetail(campaignId, aid);
      });
      card.style.cursor = 'pointer';
    });
  };

  // ─── UTILS ───────────────────────────────────────────────────────────

  CampaignOS._timeAgo = function(isoString) {
    if (!isoString) return '—';
    var now = new Date();
    var then = new Date(isoString);
    var diff = Math.floor((now - then) / 1000);
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  };

  // ─── ASSET DETAIL MODAL ─────────────────────────────────────────────

  window.showAssetDetail = function(campaignId, assetId) {
    var state = CampaignOS.getState();
    var campaign = state.campaigns.find(function(c) { return c.id === campaignId; });
    var asset = campaign ? campaign.assets.find(function(a) { return a.id === assetId; }) : null;
    if (!asset) return;

    // Remove existing modal
    var existing = document.querySelector('.asset-modal');
    if (existing) existing.remove();

    var labelLower = asset.label ? asset.label.toLowerCase() : 'generated';
    var modal = document.createElement('div');
    modal.className = 'asset-modal';
    modal.innerHTML =
      '<div class="modal-overlay" onclick="this.parentElement.remove()"></div>' +
      '<div class="modal-content">' +
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">' +
          '<h2 style="font-size:22px;margin:0">' + asset.title + '</h2>' +
          '<div class="modal-badge badge-' + labelLower + '">' + (asset.label || 'GENERATED') + '</div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;margin-bottom:16px">' +
          '<span class="tag ' + asset.type + '">' + (asset.type ? asset.type.charAt(0).toUpperCase() + asset.type.slice(1) : 'Asset') + '</span>' +
          '<span style="font-size:12px;color:var(--text-dim)">' + asset.stage + '</span>' +
        '</div>' +
        '<p class="modal-hook">' + asset.hook + '</p>' +
        '<p class="modal-caption" style="white-space:pre-wrap">' + asset.caption + '</p>' +
        '<div style="margin-top:16px;font-size:12px;color:var(--text-dim)">' +
          (asset.scheduledDate ? '📅 Scheduled: ' + asset.scheduledDate + (asset.scheduledTime ? ' at ' + asset.scheduledTime.split('T')[1].slice(0,5) : '') : '📅 Not scheduled') +
        '</div>' +
        '<div class="modal-actions">' +
          '<button onclick="CampaignOS.approveAsset(\'' + campaignId + '\',\'' + assetId + '\');document.querySelector(\'.asset-modal\').remove()">Approve</button>' +
          '<button onclick="CampaignOS.publishAsset(\'' + campaignId + '\',\'' + assetId + '\');document.querySelector(\'.asset-modal\').remove()">Publish</button>' +
          '<button onclick="CampaignOS.archiveAsset(\'' + campaignId + '\',\'' + assetId + '\');document.querySelector(\'.asset-modal\').remove()">Archive</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);
  };

})();
