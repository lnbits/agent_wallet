const TEMPLATE_OPTIONS = [
  {label: 'Agent Wallet', value: 'agent_wallet'},
  {label: 'Receive-only', value: 'receive_only'},
  {label: 'Micro-spend', value: 'micro_spend'},
  {label: 'Developer sandbox', value: 'sandbox'},
  {label: 'Business controlled', value: 'business'}
]

const POLICY_PRESETS = {
  agent_wallet: {
    single_payment_limit_sats: 100,
    daily_limit_sats: 1000,
    allow_spending: false,
    allow_lnurl_pay: false,
    allow_lightning_address_pay: false,
    allow_lnurl_withdraw: false,
    dry_run_required: true,
    approval_required_above_sats: null
  },
  receive_only: {
    single_payment_limit_sats: 0,
    daily_limit_sats: 0,
    allow_spending: false,
    allow_lnurl_pay: false,
    allow_lightning_address_pay: false,
    allow_lnurl_withdraw: false,
    dry_run_required: true,
    approval_required_above_sats: null
  },
  micro_spend: {
    single_payment_limit_sats: 21,
    daily_limit_sats: 210,
    allow_spending: true,
    allow_lnurl_pay: true,
    allow_lightning_address_pay: false,
    allow_lnurl_withdraw: false,
    dry_run_required: false,
    approval_required_above_sats: 100
  },
  sandbox: {
    single_payment_limit_sats: 10,
    daily_limit_sats: 100,
    allow_spending: true,
    allow_lnurl_pay: true,
    allow_lightning_address_pay: true,
    allow_lnurl_withdraw: false,
    dry_run_required: true,
    approval_required_above_sats: 21
  },
  business: {
    single_payment_limit_sats: 1000,
    daily_limit_sats: 10000,
    allow_spending: true,
    allow_lnurl_pay: true,
    allow_lightning_address_pay: true,
    allow_lnurl_withdraw: false,
    dry_run_required: true,
    approval_required_above_sats: 1000
  }
}

const PROFILE_COLUMNS = [
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
]

const ACTIVITY_COLUMNS = [
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
]

const defaultPolicy = template => ({
  ...(POLICY_PRESETS[template] || POLICY_PRESETS.agent_wallet)
})

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
        data: {},
        policy: {}
      },
      templateOptions: TEMPLATE_OPTIONS,
      profileTable: {
        columns: PROFILE_COLUMNS
      },
      activityTable: {
        columns: ACTIVITY_COLUMNS
      }
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
        label: link.label,
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
    async getProfiles() {
      this.loading = true
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/agent_wallet/api/v1/profiles/paginated'
        )
        this.profiles = data.data || []
      } catch (error) {
        LNbits.utils.notifyApiError(error)
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
        LNbits.utils.notifyApiError(error)
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
        LNbits.utils.notifyApiError(error)
      }
    },
    async getLnurlpLinks() {
      if (!this.g.user.wallets?.length) {
        this.lnurlpLinks = []
        return
      }
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/lnurlp/api/v1/links?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        this.lnurlpLinks = data.map(this.lnurlpOption)
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async enableLnurlp() {
      try {
        await LNbits.api.request('PUT', '/api/v1/extension/lnurlp/enable', null)
        this.$q.notify({type: 'positive', message: 'LNURLp enabled.'})
        await this.getLnurlpStatus()
        this.getLnurlpLinks()
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    applyTemplate(template) {
      this.profileDialog.policy = defaultPolicy(template)
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
      this.profileDialog.policy = defaultPolicy(
        this.profileDialog.data.template
      )
      if (profile) this.getPolicy(profile.id)
      this.profileDialog.show = true
    },
    closeProfileDialog() {
      this.profileDialog.data = {}
      this.profileDialog.policy = {}
    },
    async getPolicy(profileId) {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/agent_wallet/api/v1/profiles/${profileId}/policy`
        )
        this.profileDialog.policy = data
      } catch (error) {
        if (error.response?.status === 404) {
          this.$q.notify({
            type: 'warning',
            message: 'Policy not found. Using template defaults.'
          })
          return
        }
        LNbits.utils.notifyApiError(error)
      }
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
    lnurlpOption(link) {
      const domain = link.domain || window.location.host
      const lnaddress = link.username ? `${link.username}@${domain}` : null
      const lnurlp = link.lnurlp
      const amount = link.currency
        ? `${link.min}-${link.max} ${link.currency}`
        : `${link.min}-${link.max} sats`
      return {
        ...link,
        lnaddress,
        lnurlp,
        label: `${link.description} / ${amount}${link.username ? ` / ${link.username}` : ''}`
      }
    },
    applyLnurlpLink(linkId) {
      const link = this.lnurlpLinks.find(l => l.id === linkId)
      if (!link) {
        this.profileDialog.data.lnurlp_id = ''
        this.profileDialog.data.lightning_address = ''
        return
      }
      this.profileDialog.data.lnurlp_id = link.id
      this.profileDialog.data.lightning_address = link.lnaddress || ''
    },
    async saveProfile() {
      if (this.profileDialog.data.id) {
        await this.updateProfile()
        return
      }
      await this.createProfile()
    },
    async createProfile() {
      const payload = {
        ...this.profileDialog.data,
        policy: this.profileDialog.policy
      }
      try {
        const {data: profile} = await LNbits.api.request(
          'POST',
          '/agent_wallet/api/v1/profiles',
          null,
          payload
        )
        this.profileDialog.show = false
        await this.getProfiles()
        this.$q.notify({
          type: 'positive',
          message: `Agent wallet ${profile.name} saved.`
        })
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async updateProfile() {
      const payload = {...this.profileDialog.data}
      try {
        const {data: profile} = await LNbits.api.request(
          'PUT',
          `/agent_wallet/api/v1/profiles/${payload.id}`,
          null,
          payload
        )
        await LNbits.api.request(
          'PUT',
          `/agent_wallet/api/v1/profiles/${payload.id}/policy`,
          null,
          this.profileDialog.policy
        )
        this.profileDialog.show = false
        await this.getProfiles()
        this.$q.notify({
          type: 'positive',
          message: `Agent wallet ${profile.name} saved.`
        })
      } catch (error) {
        LNbits.utils.notifyApiError(error)
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
        if (error) LNbits.utils.notifyApiError(error)
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
    mcpServerName(profile) {
      return `lnbits_agent_wallet_${profile.name || profile.id}`
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '_')
    },
    mcpConfig(profile) {
      return {
        mcpServers: {
          [this.mcpServerName(profile)]: {
            command: 'uv',
            args: ['run', 'lnbits-agent-mcp'],
            env: {
              LNBITS_URL: window.location.origin,
              LNBITS_AGENT_TOKEN: 'PASTE_RESTRICTED_ACL_BEARER_TOKEN_HERE',
              LNBITS_AGENT_PROFILE_ID: profile.id
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
    copyMcpCommand() {
      LNbits.utils.copyText('uv run lnbits-agent-mcp')
      this.$q.notify({type: 'positive', message: 'MCP command copied.'})
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
        LNbits.utils.notifyApiError(error)
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
