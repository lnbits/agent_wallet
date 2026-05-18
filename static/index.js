window.PageAgentWallet = {
  template: '#page-agent_wallet',
  delimiters: ['${', '}'],
  data() {
    return {
      loading: false,
      profiles: [],
      tokens: [],
      lnurlpLinks: [],
      activityByProfile: {},
      loadingActivityByProfile: {},
      lnurlpStatus: null,
      profileDialog: {
        show: false,
        selectedTokenId: null,
        selectedLnurlpId: null,
        data: {},
        policy: {}
      },
      profileColumns: [
        {name: 'actions', align: 'left', label: '', field: 'actions'},
        {
          name: 'name',
          align: 'left',
          label: 'Name',
          field: 'name',
          sortable: true
        },
        {name: 'wallet', align: 'left', label: 'Wallet', field: 'wallet'},
        {name: 'template', align: 'left', label: 'Template', field: 'template'},
        {
          name: 'token_name',
          align: 'left',
          label: 'Token',
          field: 'token_name'
        },
        {name: 'status', align: 'left', label: 'Status', field: 'status'},
        {
          name: 'lightning_address',
          align: 'left',
          label: 'Lightning Address',
          field: 'lightning_address'
        }
      ],
      activityColumns: [
        {
          name: 'event_type',
          align: 'left',
          label: 'Event',
          field: 'event_type'
        },
        {
          name: 'amount_sats',
          align: 'left',
          label: 'Sats',
          field: 'amount_sats'
        },
        {
          name: 'destination',
          align: 'left',
          label: 'Destination',
          field: 'destination'
        },
        {name: 'status', align: 'left', label: 'Status', field: 'status'},
        {
          name: 'created_at',
          align: 'left',
          label: 'Created',
          field: 'created_at'
        }
      ],
      templateOptions: [
        {label: 'Agent Wallet', value: 'agent_wallet'},
        {label: 'Receive-only', value: 'receive_only'},
        {label: 'Micro-spend', value: 'micro_spend'},
        {label: 'Developer sandbox', value: 'sandbox'},
        {label: 'Business controlled', value: 'business'}
      ]
    }
  },
  computed: {
    walletOptions() {
      const wallets = (this.g.user && this.g.user.wallets) || []
      return wallets.map(w => ({label: w.name || w.id, value: w.id}))
    },
    tokenOptions() {
      return this.tokens.map(t => ({
        label: `${t.acl_name} / ${t.token_name || t.token_hint || t.token_id}`,
        value: t.token_id
      }))
    },
    lnurlpOptions() {
      return this.lnurlpLinks.map(link => ({
        label: this.lnurlpLabel(link),
        value: link.id
      }))
    },
    canSaveProfile() {
      return Boolean(
        this.profileDialog.data.name &&
          this.profileDialog.data.wallet &&
          this.profileDialog.data.acl_id &&
          this.profileDialog.data.token_id
      )
    },
    profileDialogTitle() {
      return `${this.profileDialog.data.id ? 'Edit' : 'Create'} agent wallet`
    },
    profileSubmitLabel() {
      return this.profileDialog.data.id
        ? 'Update agent wallet'
        : 'Create agent wallet'
    }
  },
  methods: {
    notifyApiError(error) {
      LNbits.utils.notifyApiError(error)
    },
    async getProfiles() {
      this.loading = true
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/agent_wallet/api/v1/profiles/paginated'
        )
        this.profiles = data.data || []
      } catch (error) {
        this.notifyApiError(error)
      }
      this.loading = false
    },
    async getTokens() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/agent_wallet/api/v1/tokens'
        )
        this.tokens = data
      } catch (error) {
        this.notifyApiError(error)
      }
    },
    async getLnurlpStatus() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/agent_wallet/api/v1/lnurlp/status'
        )
        this.lnurlpStatus = data
      } catch (error) {
        this.notifyApiError(error)
      }
    },
    getLnurlpLinks() {
      if (!this.g.user.wallets?.length) {
        this.lnurlpLinks = []
        return
      }
      LNbits.api
        .request(
          'GET',
          '/lnurlp/api/v1/links?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.lnurlpLinks = response.data.map(this.mapLnurlpLink)
        })
        .catch(LNbits.utils.notifyApiError)
    },
    async enableLnurlp() {
      try {
        await LNbits.api.request('PUT', '/api/v1/extension/lnurlp/enable', null)
        this.$q.notify({type: 'positive', message: 'LNURLp enabled.'})
        await this.getLnurlpStatus()
        this.getLnurlpLinks()
      } catch (error) {
        this.notifyApiError(error)
      }
    },
    defaultPolicy() {
      return {
        single_payment_limit_sats: 100,
        daily_limit_sats: 1000,
        allow_spending: false,
        allow_lnurl_pay: false,
        allow_lightning_address_pay: false,
        allow_lnurl_withdraw: false,
        dry_run_required: true
      }
    },
    showProfileForm(profile) {
      this.profileDialog.data = profile
        ? {...profile}
        : {
            wallet: this.walletOptions[0] && this.walletOptions[0].value,
            name: '',
            description: '',
            template: 'agent_wallet',
            acl_id: '',
            token_id: '',
            token_name: '',
            token_hint: '',
            status: 'active',
            lightning_address: '',
            lnurlp_id: ''
          }
      this.profileDialog.policy = this.defaultPolicy()
      this.profileDialog.selectedTokenId = profile ? profile.token_id : null
      this.profileDialog.selectedLnurlpId = profile ? profile.lnurlp_id : null
      if (profile) this.getPolicy(profile.id)
      this.profileDialog.show = true
    },
    closeProfileDialog() {
      this.profileDialog.data = {}
      this.profileDialog.policy = {}
      this.profileDialog.selectedTokenId = null
      this.profileDialog.selectedLnurlpId = null
    },
    async getPolicy(profileId) {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/agent_wallet/api/v1/profiles/${profileId}/policy`
        )
        this.profileDialog.policy = data
      } catch (_) {}
    },
    applyToken(tokenId) {
      const token = this.tokens.find(t => t.token_id === tokenId)
      if (!token) {
        this.profileDialog.data.acl_id = ''
        this.profileDialog.data.token_id = ''
        this.profileDialog.data.token_name = ''
        this.profileDialog.data.token_hint = ''
        return
      }
      this.profileDialog.data.acl_id = token.acl_id
      this.profileDialog.data.token_id = token.token_id
      this.profileDialog.data.token_name = token.token_name
      this.profileDialog.data.token_hint = token.token_hint
    },
    lnaddress(link) {
      const domain = link.domain || window.location.host
      return `${link.username}@${domain}`
    },
    mapLnurlpLink(link) {
      return {
        ...link,
        lnaddress: link.username ? this.lnaddress(link) : null,
        lnurlp: `https://${link.domain || window.location.host}/lnurlp/${link.id}`
      }
    },
    lnurlpLabel(link) {
      const target = link.lnaddress || link.lnurlp
      const amount = link.currency
        ? `${link.min}-${link.max} ${link.currency}`
        : `${link.min}-${link.max} sats`
      return `${link.description} / ${target} / ${amount}`
    },
    applyLnurlpLink(linkId) {
      const link = this.lnurlpLinks.find(l => l.id === linkId)
      if (!link) {
        this.profileDialog.data.lnurlp_id = ''
        this.profileDialog.data.lightning_address = ''
        return
      }
      this.profileDialog.data.lnurlp_id = link.id
      this.profileDialog.data.lightning_address =
        link.lnaddress || link.lnurlp || ''
    },
    async saveProfile() {
      const data = {
        ...this.profileDialog.data,
        policy: this.profileDialog.policy
      }
      const method = data.id ? 'PUT' : 'POST'
      const url = data.id
        ? `/agent_wallet/api/v1/profiles/${data.id}`
        : '/agent_wallet/api/v1/profiles'
      try {
        const {data: profile} = await LNbits.api.request(
          method,
          url,
          null,
          data
        )
        if (data.id) {
          await LNbits.api.request(
            'PUT',
            `/agent_wallet/api/v1/profiles/${data.id}/policy`,
            null,
            this.profileDialog.policy
          )
        }
        this.profileDialog.show = false
        await this.getProfiles()
        this.$q.notify({
          type: 'positive',
          message: `Agent wallet ${profile.name} saved.`
        })
      } catch (error) {
        this.notifyApiError(error)
      }
    },
    async deleteProfile(profile) {
      try {
        await LNbits.utils.confirmDialog(`Delete agent wallet ${profile.name}?`)
        await LNbits.api.request(
          'DELETE',
          `/agent_wallet/api/v1/profiles/${profile.id}`
        )
        await this.getProfiles()
      } catch (error) {
        if (error) this.notifyApiError(error)
      }
    },
    toggleProfileExpansion(props) {
      props.expand = !props.expand
      if (props.expand) this.getProfileActivity(props.row)
    },
    activityRows(profile) {
      return this.activityByProfile[profile.id] || []
    },
    activityLoading(profile) {
      return Boolean(this.loadingActivityByProfile[profile.id])
    },
    mcpServerUrl(profile) {
      return `${window.location.origin}/agent_wallet/api/v1/mcp/${profile.id}`
    },
    mcpServerName(profile) {
      return `agent_wallet_${profile.name || profile.id}`
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '_')
    },
    mcpConfig(profile) {
      return {
        mcpServers: {
          [this.mcpServerName(profile)]: {
            url: this.mcpServerUrl(profile),
            headers: {
              Authorization: 'Bearer PASTE_AGENT_TOKEN_SECRET_HERE'
            }
          }
        }
      }
    },
    mcpConfigJson(profile) {
      return JSON.stringify(this.mcpConfig(profile), null, 2)
    },
    copyMcpConfig(profile) {
      LNbits.utils.copyText(this.mcpConfigJson(profile))
      this.$q.notify({type: 'positive', message: 'MCP config copied.'})
    },
    copyMcpServerUrl(profile) {
      LNbits.utils.copyText(this.mcpServerUrl(profile))
      this.$q.notify({type: 'positive', message: 'MCP server URL copied.'})
    },
    async getProfileActivity(profile) {
      this.loadingActivityByProfile = {
        ...this.loadingActivityByProfile,
        [profile.id]: true
      }
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/agent_wallet/api/v1/profiles/${profile.id}/activity`
        )
        this.activityByProfile = {
          ...this.activityByProfile,
          [profile.id]: data.data || []
        }
      } catch (error) {
        this.notifyApiError(error)
      }
      this.loadingActivityByProfile = {
        ...this.loadingActivityByProfile,
        [profile.id]: false
      }
    }
  },
  async created() {
    await Promise.all([
      this.getProfiles(),
      this.getTokens(),
      this.getLnurlpStatus()
    ])
    this.getLnurlpLinks()
  }
}
