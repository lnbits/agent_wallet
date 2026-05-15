<template id="page-agent_wallet">
  <div class="row q-col-gutter-md">
    <div class="col-12 col-md-8 col-lg-7 q-gutter-y-md">
    

      <div class="q-mt-lg">
        <span class="text-h5">Profiles</span>
      </div>
      <q-card
        id="profilesCard"
        class="q-mt-xs"
      >
        <q-card-section
          class=""
        >
          <div class="row items-center no-wrap q-mb-md">
            <div class="col">
              <q-input
                :label="$t('search')"
                dense
                class="q-pr-xl"
                v-model="profilesTable.search"
              >
                <template v-slot:before>
                  <q-icon name="search"> </q-icon>
                </template>
                <template v-slot:append>
                  <q-icon
                    v-if="profilesTable.search !== ''"
                    name="close"
                    @click="profilesTable.search = ''"
                    class="cursor-pointer"
                  >
                  </q-icon>
                </template>
              </q-input>
            </div>
            <div class="col-auto">
              
              <q-btn
                @click="showNewProfilesForm()"
                unelevated
                split
                color="primary"
              >
                New Profiles
              </q-btn>
              
              <q-btn
                flat
                color="grey"
                icon="file_download"
                @click="exportProfilesCSV"
                >CSV</q-btn
              >
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="profilesList"
            row-key="id"
            :columns="profilesTable.columns"
            v-model:pagination="profilesTable.pagination"
            :loading="profilesTable.loading"
            @request="getProfiles"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  ${ col.label }
                </q-th>
              </q-tr>
            </template>

            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td auto-width>
                   
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="showEditProfilesForm(props.row)"
                    icon="edit"
                    color="light-blue"
                    class="q-mr-sm"
                  >
                    <q-tooltip> Edit </q-tooltip>
                  </q-btn>
                  
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="deleteProfiles(props.row.id)"
                    icon="cancel"
                    color="pink"
                    class="q-mr-sm"
                  >
                    <q-tooltip> Delete </q-tooltip>
                  </q-btn>
                </q-td>

                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <div v-if="col.field == 'updated_at'">
                    <span v-text="dateFromNow(col.value)"> </span>
                  </div>
                  <div v-else>${ col.value }</div>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>

      <div class="q-mt-lg">
        <span class="text-h5">Client Data</span>
      </div>
      <q-card
        id="clientDataCard"
        class="q-mt-xs"
      >
        <q-card-section
          class=""
        >
          <div class="row items-center no-wrap q-mb-md">
            <div class="col">
              <q-input
                :label="$t('search')"
                dense
                class="q-pr-xl"
                v-model="clientDataTable.search"
              >
                <template v-slot:before>
                  <q-icon name="search"> </q-icon>
                </template>
                <template v-slot:append>
                  <q-icon
                    v-if="clientDataTable.search !== ''"
                    name="close"
                    @click="clientDataTable.search = ''"
                    class="cursor-pointer"
                  >
                  </q-icon>
                </template>
              </q-input>
            </div>
            <div class="col-auto">
              <q-select
                filled
                dense
                v-model="clientDataFormDialog.profiles"
                :options="[
                  {label: 'All Profiles', value: ''},
                  ...profilesList.map(x => ({
                    label: x.name || x.id,
                    value: x.id
                  }))
                ]"
                label="Profiles"
                class="q-mb-md"
              ></q-select>
            </div>
            <div class="col-auto">
              <q-btn
                flat
                color="grey"
                icon="file_download"
                class="q-mb-md"
                @click="exportClientDataCSV"
                >CSV</q-btn
              >
            </div>
          </div>
          <q-table
            dense
            flat
            :rows="clientDataList"
            row-key="id"
            :columns="clientDataTable.columns"
            v-model:pagination="clientDataTable.pagination"
            :loading="clientDataTable.loading"
            @request="getClientData"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  ${ col.label }
                </q-th>
              </q-tr>
            </template>

            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td auto-width>
                  
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="showEditClientDataForm(props.row)"
                    icon="edit"
                    color="light-blue"
                    class="q-mr-sm"
                  >
                    <q-tooltip> Edit </q-tooltip>
                  </q-btn>
                  
                  <q-btn
                    flat
                    dense
                    size="xs"
                    @click="deleteClientData(props.row.id)"
                    icon="cancel"
                    color="pink"
                    class="q-mr-sm"
                  >
                    <q-tooltip> Delete </q-tooltip>
                  </q-btn>
                </q-td>

                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <div v-if="col.field == 'updated_at'">
                    <span v-text="dateFromNow(col.value)"> </span>
                  </div>
                  <div v-else>${ col.value }</div>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>
    
    <div class="col-12 col-md-4 col-lg-5 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <h6 class="text-subtitle1 q-my-none">Agent Wallet</h6>
          <p>Lightning wallets for AI agents</p>
        </q-card-section>
        <q-card-section class="q-pa-none">
          <q-separator></q-separator>
          <q-list>
            <!-- {% include "agent_wallet/_api_docs.html" %} -->
            <q-separator></q-separator>
            <q-expansion-item group="extras" icon="info" label="More info">
              <q-card>
                <q-card-section>
                  <p>Some more info about Agent Wallet.</p>
                  <small
                    >Created by
                    <a
                      class="text-secondary"
                      href="https://github.com/lnbits"
                      target="_blank"
                      >LNbits extension builder</a
                    >.</small
                  >
                </q-card-section>
              </q-card>
            </q-expansion-item>
          </q-list>
        </q-card-section>
      </q-card>
    </div>
    

    <!--/////////////////////////////////////////////////-->
    <!--//////////////FORM DIALOG////////////////////////-->
    <!--/////////////////////////////////////////////////-->


    <q-dialog v-model="profilesFormDialog.show" position="top">
      <q-card
        v-if="profilesFormDialog.show"
        class="q-pa-lg q-pt-md lnbits__dialog-card q-col-gutter-md"
      >
        <span class="text-h5">Profiles</span>

       
<q-input
  filled
  dense
  v-model.trim="profilesFormDialog.data.name"
  label="Name"
  hint=" "
></q-input>
  
<q-input
  filled
  dense
  v-model.trim="profilesFormDialog.data.description"
  label="Description"
  hint="  (optional)"
></q-input>
  
<q-input
  filled
  dense
  v-model.trim="profilesFormDialog.data.status"
  label="Status"
  hint=" "
></q-input>
  
<q-input
  filled
  dense
  v-model.trim="profilesFormDialog.data.lnurlp_id"
  label="LNURL"
  hint="  (optional)"
></q-input>
 
        <div class="row q-mt-lg">
          <q-btn @click="saveProfiles" unelevated color="primary">
            <span v-if="profilesFormDialog.data.id">Update</span>
            <span v-else>Create</span>
          </q-btn>
          <q-btn v-close-popup flat color="grey" class="q-ml-auto"
            >Cancel</q-btn
          >
        </div>
      </q-card>
    </q-dialog>

    <q-dialog v-model="clientDataFormDialog.show" position="top">
      <q-card
        v-if="clientDataFormDialog.show"
        class="q-pa-lg q-pt-md lnbits__dialog-card q-col-gutter-md"
      >
        <span class="text-h5">Client Data</span>

       
<q-input
  filled
  dense
  v-model.trim="clientDataFormDialog.data.name"
  label="Name"
  hint="  (optional)"
></q-input>
 
        <div class="row q-mt-lg">
          <q-btn @click="saveClientData" unelevated color="primary">
            <span v-if="clientDataFormDialog.data.id">Update</span>
            <span v-else>Create</span>
          </q-btn>
          <q-btn v-close-popup flat color="grey" class="q-ml-auto"
            >Cancel</q-btn
          >
        </div>
      </q-card>
    </q-dialog>
  </div>
</template>