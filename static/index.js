window.PageAgentWallet = {
  template: '#page-agent_wallet',
  delimiters: ['${', '}'],
  data: function () {
    return {
      currencyOptions: ['sat'],
      settingsFormDialog: {
        show: false,
        data: {}
      },

      profilesFormDialog: {
        show: false,
        data: {
          name: null,
          description: null,
          status: null,
          lnurlp_id: null,
          
        }
      },
      profilesList: [],
      profilesTable: {
        search: '',
        loading: false,
        columns: [
          {"name": "name", "align": "left", "label": "Name", "field": "name", "sortable": true},
          {"name": "token_name", "align": "left", "label": "Token Name", "field": "token_name", "sortable": true},
          {"name": "status", "align": "left", "label": "Status", "field": "status", "sortable": true},
          {"name": "expires_at", "align": "left", "label": "Expires at", "field": "expires_at", "sortable": true},
          {"name": "updated_at", "align": "left", "label": "Updated At", "field": "updated_at", "sortable": true},
          {"name": "id", "align": "left", "label": "ID", "field": "id", "sortable": true},
          
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      },

      clientDataFormDialog: {
        show: false,
        profiles: {label: 'All Profiles', value: ''},
        data: {}
      },
      clientDataList: [],
      clientDataTable: {
        search: '',
        loading: false,
        columns: [
          {"name": "name", "align": "left", "label": "Name", "field": "name", "sortable": true},
          {"name": "updated_at", "align": "left", "label": "Updated At", "field": "updated_at", "sortable": true},
          {"name": "id", "align": "left", "label": "ID", "field": "id", "sortable": true},
          
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      }
    }
  },
  watch: {
    'profilesTable.search': {
      handler() {
        const props = {}
        if (this.profilesTable.search) {
          props['search'] = this.profilesTable.search
        }
        this.getProfiles()
      }
    },
    'clientDataTable.search': {
      handler() {
        const props = {}
        if (this.clientDataTable.search) {
          props['search'] = this.clientDataTable.search
        }
        this.getClientData()
      }
    },
    'clientDataFormDialog.profiles.value': {
      handler() {
        const props = {}
        if (this.clientDataTable.search) {
          props['search'] = this.clientDataTable.search
        }
        this.getClientData()
      }
    }
  },

  methods: {

    //////////////// Profiles ////////////////////////
    async showNewProfilesForm() {
      this.profilesFormDialog.data = {
          name: null,
          description: null,
          status: null,
          lnurlp_id: null,
          
      }
      this.profilesFormDialog.show = true
    },
    async showEditProfilesForm(data) {
      this.profilesFormDialog.data = {...data}
      this.profilesFormDialog.show = true
    },
    async saveProfiles() {
      
      try {
        const data = {extra: {}, ...this.profilesFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/agent_wallet/api/v1/profiles' + entry,
          null,
          data
        )
        this.getProfiles()
        this.profilesFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getProfiles(props) {
      
      try {
        this.profilesTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(
          this.profilesTable,
          props
        )
        const {data} = await LNbits.api.request(
          'GET',
          `/agent_wallet/api/v1/profiles/paginated?${params}`,
          null
        )
        this.profilesList = data.data
        this.profilesTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.profilesTable.loading = false
      }
    },
    async deleteProfiles(profilesId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Profiles?')
        .onOk(async () => {
          try {
            
            await LNbits.api.request(
              'DELETE',
              '/agent_wallet/api/v1/profiles/' + profilesId,
              null
            )
            await this.getProfiles()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async exportProfilesCSV() {
      await LNbits.utils.exportCSV(
        this.profilesTable.columns,
        this.profilesList,
        'profiles_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Client Data ////////////////////////
    async showEditClientDataForm(data) {
      this.clientDataFormDialog.data = {...data}
      this.clientDataFormDialog.show = true
    },
    async saveClientData() {
      
      try {
        const data = {extra: {}, ...this.clientDataFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/agent_wallet/api/v1/client_data' + entry,
          null,
          data
        )
        this.getClientData()
        this.clientDataFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getClientData(props) {
      
      try {
        this.clientDataTable.loading = true
        let params = LNbits.utils.prepareFilterQuery(
          this.clientDataTable,
          props
        )
        const profilesId = this.clientDataFormDialog.profiles.value
        if (profilesId) {
          params += `&profiles_id=${profilesId}`
        }
        const {data} = await LNbits.api.request(
          'GET',
          `/agent_wallet/api/v1/client_data/paginated?${params}`,
          null
        )
        this.clientDataList = data.data
        this.clientDataTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.clientDataTable.loading = false
      }
    },
    async deleteClientData(clientDataId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Client Data?')
        .onOk(async () => {
          try {
            
            await LNbits.api.request(
              'DELETE',
              '/agent_wallet/api/v1/client_data/' + clientDataId,
              null
            )
            await this.getClientData()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },

    async exportClientDataCSV() {
      await LNbits.utils.exportCSV(
        this.clientDataTable.columns,
        this.clientDataList,
        'client_data_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Utils ////////////////////////
    dateFromNow(date) {
      return moment(date).fromNow()
    },
    async fetchCurrencies() {
      try {
        const response = await LNbits.api.request('GET', '/api/v1/currencies')
        this.currencyOptions = ['sat', ...response.data]
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    }
  },
  ///////////////////////////////////////////////////
  //////LIFECYCLE FUNCTIONS RUNNING ON PAGE LOAD/////
  ///////////////////////////////////////////////////
  async created() {
    this.fetchCurrencies()
    this.getProfiles()
    this.getClientData()

    
    
  }
}