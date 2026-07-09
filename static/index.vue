<template id="page-agent_wallet">
  <div class="row q-col-gutter-md">
    <div class="col-12 col-md-8 q-gutter-y-md">
      <q-card>
        <q-card-section>
          <div class="row items-center q-mb-md">
            <div class="col">
              <div class="text-h5">Agent Wallets</div>
              <div class="text-caption text-grey">
                Bind pre-created ACL tokens to agent wallet profiles.
              </div>
            </div>
            <q-btn color="primary" unelevated @click="showProfileForm()">
              New agent wallet
            </q-btn>
          </div>

          <q-banner
            v-if="lnurlpStatus && !lnurlpStatus.enabled"
            class="bg-orange-1 q-mb-md"
          >
            <span v-text="lnurlpStatus.message"></span>
            <template v-slot:action>
              <q-btn
                flat
                color="primary"
                @click="enableLnurlp"
                :disable="!lnurlpStatus.installed"
              >
                Enable LNURLp
              </q-btn>
            </template>
          </q-banner>

          <q-table
            dense
            flat
            :rows="profiles"
            :columns="profileTable.columns"
            row-key="id"
            :loading="loading"
          >
            <template v-slot:header="props">
              <q-tr :props="props">
                <q-th auto-width></q-th>
                <q-th v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.label"> </span>
                </q-th>
              </q-tr>
            </template>
            <template v-slot:body="props">
              <q-tr :props="props">
                <q-td auto-width>
                  <q-btn
                    size="sm"
                    color="accent"
                    round
                    dense
                    @click="toggleProfileExpansion(props)"
                    :icon="props.expand ? 'expand_less' : 'expand_more'"
                  >
                    <q-tooltip>Connector and activity</q-tooltip>
                  </q-btn>
                  <q-btn
                    flat
                    dense
                    size="sm"
                    icon="edit"
                    color="light-blue"
                    class="q-ml-xs"
                    @click="showProfileForm(props.row)"
                  >
                    <q-tooltip>Edit</q-tooltip>
                  </q-btn>
                  <q-btn
                    flat
                    dense
                    size="sm"
                    icon="delete"
                    color="negative"
                    class="q-ml-xs"
                    @click="deleteProfile(props.row)"
                  >
                    <q-tooltip>Delete</q-tooltip>
                  </q-btn>
                </q-td>
                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                  <span v-text="col.value"></span>
                </q-td>
              </q-tr>
              <q-tr v-show="props.expand" :props="props">
                <q-td colspan="100%">
                  <q-list>
                    <q-expansion-item
                      group="wallet-activity"
                      icon="history"
                      label="Activity"
                      default-opened
                    >
                      <q-table
                        dense
                        flat
                        :rows="activityRows(props.row)"
                        :columns="activityTable.columns"
                        row-key="id"
                        :loading="activityLoading(props.row)"
                      >
                        <template v-slot:body="props">
                          <q-tr :props="props">
                            <q-td
                              v-for="col in props.cols"
                              :key="col.name"
                              :props="props"
                            >
                              <div
                                v-if="col.name === 'destination' && col.value"
                              >
                                <span
                                  v-text="
                                    `${col.value.slice(0, 12)} ... ${col.value.slice(-12)}`
                                  "
                                ></span>
                                <q-btn
                                  flat
                                  dense
                                  size="sm"
                                  icon="content_copy"
                                  color="grey"
                                  class="q-ml-xs"
                                  @click="utils.copyText(col.value)"
                                >
                                  <q-tooltip>Copy destination</q-tooltip>
                                </q-btn>
                              </div>
                              <span v-else v-text="col.value"></span>
                            </q-td>
                          </q-tr>
                        </template>
                      </q-table>
                    </q-expansion-item>

                    <q-separator></q-separator>

                    <q-expansion-item
                      group="wallet-activity"
                      icon="settings_ethernet"
                      label="MCP connector"
                    >
                      <q-card>
                        <q-card-section>
                          <div class="text-caption text-grey q-mb-sm">
                            Run the upstream LNbits MCP server beside your
                            agent. Paste a restricted ACL bearer token before
                            use.
                          </div>
                          <q-input
                            filled
                            dense
                            readonly
                            type="textarea"
                            :model-value="mcpConfigJson(props.row)"
                            rows="14"
                          ></q-input>
                        </q-card-section>
                        <q-card-actions>
                          <q-btn
                            dense
                            flat
                            color="secondary"
                            icon="psychology"
                            label="Copy for my AI agent"
                            @click="copyAgentPrompt(props.row)"
                          ></q-btn>
                          <q-btn
                            dense
                            flat
                            color="primary"
                            icon="content_copy"
                            label="Copy MCP JSON"
                            @click="
                              utils.copyText(
                                mcpConfigJson(props.row),
                                'MCP config copied'
                              )
                            "
                          ></q-btn>
                        </q-card-actions>
                      </q-card>
                    </q-expansion-item>
                  </q-list>
                </q-td>
              </q-tr>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>

    <div class="col-12 col-md-4">
      <q-card>
        <q-card-section>
          <div class="text-h6">MVP notes</div>
          <ul class="q-pl-md">
            <li>Create the ACL/token in LNbits first.</li>
            <li>This extension stores token refs only, not raw secrets.</li>
            <li>LNURL/Lightning Address uses the LNURLp extension.</li>
          </ul>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog
      v-model="profileDialog.show"
      position="top"
      @hide="closeProfileDialog"
    >
      <q-card
        v-if="profileDialog.show"
        class="q-pa-lg q-pt-xl lnbits__dialog-card"
      >
        <q-form @submit="saveProfile" class="q-gutter-md">
          <div>
            <div class="text-h6" v-text="profileDialogTitle"></div>
            <div class="text-caption text-grey">
              Bind an existing scoped ACL token to an agent profile. Token
              secrets are not stored here.
            </div>
          </div>

          <q-input
            filled
            dense
            v-model.trim="profileDialog.data.name"
            label="Name *"
          ></q-input>

          <q-input
            filled
            dense
            v-model.trim="profileDialog.data.description"
            label="Description"
          ></q-input>

          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-6">
              <q-select
                filled
                dense
                emit-value
                map-options
                v-model="profileDialog.data.wallet"
                :options="walletOptions"
                label="Wallet *"
              ></q-select>
            </div>
            <div class="col-12 col-md-6">
              <q-select
                filled
                dense
                emit-value
                map-options
                v-model="profileDialog.data.template"
                :options="templateOptions"
                label="Template"
                @update:model-value="applyTemplate"
              ></q-select>
            </div>
          </div>

          <q-select
            filled
            dense
            emit-value
            map-options
            clearable
            v-model="profileDialog.data.token_id"
            :options="tokenOptions"
            label="ACL token *"
            hint="Create the scoped token in LNbits first, then bind it here."
            @update:model-value="applyToken"
          ></q-select>

          <q-banner
            v-if="lnurlpStatus && !lnurlpStatus.enabled"
            rounded
            class="bg-orange-1 text-dark"
          >
            <span v-text="lnurlpStatus.message"></span>
            <template v-slot:action>
              <q-btn
                flat
                dense
                color="primary"
                @click="enableLnurlp"
                :disable="!lnurlpStatus.installed"
              >
                Enable LNURLp
              </q-btn>
            </template>
          </q-banner>

          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-6">
              <q-select
                filled
                dense
                emit-value
                map-options
                clearable
                v-model="profileDialog.data.lnurlp_id"
                :options="lnurlpOptions"
                label="LNURLp paylink"
                hint="Create the LNURLp paylink first, then choose it here."
                @update:model-value="applyLnurlpLink"
              ></q-select>
            </div>
            <div class="col-12 col-md-6">
              <q-input
                filled
                dense
                v-model.trim="profileDialog.data.lightning_address"
                label="Lightning Address / LNURLp"
                hint="Auto-filled from the selected paylink; editable if needed."
              ></q-input>
            </div>
          </div>

          <q-expansion-item
            default-opened
            group="agent-wallet-form"
            icon="policy"
            label="Policy"
            expand-separator
          >
            <div class="q-gutter-md q-pt-md">
              <div class="text-caption text-grey">
                Template presets fill these policy values. You can override them
                before saving.
              </div>

              <div class="row q-col-gutter-sm">
                <div class="col-12 col-md-4">
                  <q-input
                    filled
                    dense
                    type="number"
                    min="0"
                    v-model.number="
                      profileDialog.policy.single_payment_limit_sats
                    "
                    label="Single payment limit sats"
                  ></q-input>
                </div>
                <div class="col-12 col-md-4">
                  <q-input
                    filled
                    dense
                    type="number"
                    min="0"
                    v-model.number="profileDialog.policy.daily_limit_sats"
                    label="Daily limit sats"
                  ></q-input>
                </div>
                <div class="col-12 col-md-4">
                  <q-input
                    filled
                    dense
                    type="number"
                    min="0"
                    v-model.number="
                      profileDialog.policy.approval_required_above_sats
                    "
                    label="Approval above sats"
                  ></q-input>
                </div>
              </div>

              <div class="row q-col-gutter-sm">
                <div class="col-12 col-md-6">
                  <q-toggle
                    v-model="profileDialog.policy.allow_spending"
                    label="Allow spending"
                  ></q-toggle>
                </div>
                <div class="col-12 col-md-6">
                  <q-toggle
                    v-model="profileDialog.policy.dry_run_required"
                    label="Dry-run required"
                  ></q-toggle>
                </div>
                <div class="col-12 col-md-6">
                  <q-toggle
                    v-model="profileDialog.policy.allow_lnurl_pay"
                    label="Allow LNURL-pay"
                  ></q-toggle>
                </div>
                <div class="col-12 col-md-6">
                  <q-toggle
                    v-model="profileDialog.policy.allow_lightning_address_pay"
                    label="Allow Lightning Address pay"
                  ></q-toggle>
                </div>
                <div class="col-12 col-md-6">
                  <q-toggle
                    v-model="profileDialog.policy.allow_lnurl_withdraw"
                    label="Allow LNURL-withdraw"
                  ></q-toggle>
                </div>
              </div>
            </div>
          </q-expansion-item>

          <div class="row q-mt-lg">
            <q-btn
              unelevated
              color="primary"
              type="submit"
              :disable="!canSaveProfile"
              :label="profileSubmitLabel"
            ></q-btn>
            <q-btn v-close-popup flat color="grey" class="q-ml-auto"
              >Cancel</q-btn
            >
          </div>
        </q-form>
      </q-card>
    </q-dialog>
  </div>
</template>
