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
            ${ lnurlpStatus.message }
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
            :columns="profileColumns"
            row-key="id"
            :loading="loading"
          >
            <template v-slot:body-cell-actions="props">
              <q-td :props="props">
                <q-btn
                  flat
                  dense
                  size="sm"
                  icon="edit"
                  color="primary"
                  @click="showProfileForm(props.row)"
                >
                  <q-tooltip>Edit</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  dense
                  size="sm"
                  icon="history"
                  color="grey"
                  @click="selectProfile(props.row)"
                >
                  <q-tooltip>Activity</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  dense
                  size="sm"
                  icon="delete"
                  color="negative"
                  @click="deleteProfile(props.row)"
                >
                  <q-tooltip>Delete</q-tooltip>
                </q-btn>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>

      <q-card v-if="selectedProfile">
        <q-card-section>
          <div class="text-h6">Activity: ${ selectedProfile.name }</div>
          <q-table
            dense
            flat
            :rows="activity"
            :columns="activityColumns"
            row-key="id"
          />
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
            <div class="text-h6">
              ${ profileDialog.data.id ? 'Edit' : 'Create' } agent wallet
            </div>
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
              ></q-select>
            </div>
          </div>

          <q-select
            filled
            dense
            emit-value
            map-options
            clearable
            v-model="profileDialog.selectedTokenId"
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
            ${ lnurlpStatus.message }
            <template v-slot:action>
              <q-btn
                flat
                dense
                color="primary"
                @click="enableLnurlp"
                :disable="!lnurlpStatus.installed"
                >Enable LNURLp</q-btn
              >
            </template>
          </q-banner>

          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-6">
              <q-input
                filled
                dense
                v-model.trim="profileDialog.data.lightning_address"
                label="Lightning Address"
                hint="Optional public receive identity."
              ></q-input>
            </div>
            <div class="col-12 col-md-6">
              <q-input
                filled
                dense
                v-model.trim="profileDialog.data.lnurlp_id"
                label="LNURLp link id"
                hint="Optional LNURLp link reference."
              ></q-input>
            </div>
          </div>

          <q-expansion-item
            default-opened
            group="agent-wallet-form"
            icon="policy"
            label="Policy"
          >
            <q-card>
              <q-card-section class="q-gutter-md">
                <div class="row q-col-gutter-sm">
                  <div class="col-12 col-md-6">
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
                  <div class="col-12 col-md-6">
                    <q-input
                      filled
                      dense
                      type="number"
                      min="0"
                      v-model.number="profileDialog.policy.daily_limit_sats"
                      label="Daily limit sats"
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
              </q-card-section>
            </q-card>
          </q-expansion-item>

          <div class="row q-mt-lg">
            <q-btn
              unelevated
              color="primary"
              type="submit"
              :disable="!canSaveProfile"
              >${ profileDialog.data.id ? 'Update agent wallet' : 'Create agent
              wallet' }</q-btn
            >
            <q-btn v-close-popup flat color="grey" class="q-ml-auto"
              >Cancel</q-btn
            >
          </div>
        </q-form>
      </q-card>
    </q-dialog>
  </div>
</template>
