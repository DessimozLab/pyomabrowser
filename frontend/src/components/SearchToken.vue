<template>
  <div>
    <!-- Help Modal -->
    <div
      class="modal fade"
      data-backdrop="false"
      :id="`exampleModal_${uniqueId}`"
      tabindex="-1"
      :aria-labelledby="`exampleModalLabel${uniqueId}`"
      aria-hidden="true"
    >
      <div class="modal-dialog modal-lg modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h4 class="modal-title" :id="`exampleModalLabel${uniqueId}`">
              How to use the search in OMA Browser?
            </h4>
            <button type="button" class="close" data-dismiss="modal" aria-label="Close">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body" style="text-align: justify">
            <strong>How does the search work?</strong>
            <p>
              Input a query in the search field. Every time you press Space or Enter after a word,
              a <b>token</b> will be created. The token is composed of a <b>prefix</b> describing
              how the query should be treated and the actual <b>query</b> itself.
            </p>

            <strong>What are the different types of tokens?</strong>
            <p>
              Each token represents either a Gene, HOG, OMA group, or Taxon.
              Prefixes are used to specify which category to associate with the query term.
            </p>

            <table class="table table-bordered">
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Prefixes</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Genes</th>
                  <td>id, go, ec, description, domain, sequence</td>
                </tr>
                <tr>
                  <th scope="row">HOGs</th>
                  <td>hog, sequence</td>
                </tr>
                <tr>
                  <th scope="row">OMA Groups</th>
                  <td>omagroup, fingerprint, sequence</td>
                </tr>
                <tr>
                  <th scope="row">Taxon</th>
                  <td>species, taxid, taxon</td>
                </tr>
              </tbody>
            </table>

            <small>
              For example, the token [go:4225] will search for genes in the OMA database
              annotated with the GO:0004225 gene ontology term.
            </small>
            <br>

            <strong>How to search for a multi-word query?</strong>
            <p>
              If your query term is composed of multiple words (e.g. homo sapiens),
              use " " to encapsulate it.
            </p>

            <strong>How many tokens can I have?</strong>
            <p>
              There is no limit on the number of tokens. It is not possible to enter multiple
              tokens of different categories, except taxon, which can be combined with other
              categories. For example, you can search for 'hog:60627 species:HUMAN' to return
              human genes found in HOG:606207.
            </p>

            <strong>How to edit/delete a token?</strong>
            <p>
              To edit a query, click on it to modify the input field. To edit a prefix,
              click on the dropdown icon to select another one. To remove a token,
              click on the x to delete it.
            </p>

            <strong>Autosuggest</strong>
            <p>
              Typing a query without hitting enter or space will prompt an autosuggestion
              for the identifier after a few seconds.
            </p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Search Form -->
    <form method="POST" :id="`form_${uniqueId}`" :action="searchUrl">
      <input type="hidden" name="csrfmiddlewaretoken" :value="csrfToken">

      <div :id="`${uniqueId}_input_part`" :class="['search-input-container', multiline ? 'ml-input' : 'sl-input']">

        <!-- Help Icon -->
        <span class="material-symbols-outlined help_icon" @click="modalClicked">
          help
        </span>

        <!-- Token Container -->
        <div :id="`token-container_${uniqueId}`" :class="['token-container', multiline ? 'ml-token-con' : 'sl-token-con']">
          <span
            v-for="(token, index) in tokens"
            :key="`${token.query}-${index}`"
            class="token-input__tag"
          >
            <select class="prefix-dropdown" @change="onChangePrefix($event.target, token)">
              <template v-for="(prefixesList, prefixType) in prefixes" :key="prefixType">
                <optgroup :label="prefixType">
                  <option
                    v-for="prefix in prefixesList"
                    :key="prefix"
                    :selected="prefix === token.prefix"
                  >
                    {{ prefix }}
                  </option>
                </optgroup>
              </template>
            </select>

            <span class="vl"></span>

            <p style="display: inline" @click="detokenize(index)">
              {{ formatTokenString(token.query) }}
            </p>

            <span @click="removeToken(index)" class="token-delete">X</span>
          </span>
        </div>

        <!-- Hidden input for form submission -->
        <input type="hidden" name="hidden_query" :value="postQuery">

        <!-- Text Input -->
        <input
          type="text"
          :placeholder="placeholder"
          ref="inputHandle"
          class="token-input__text"
          :id="`input_token_search_${uniqueId}`"
          @keydown.enter="enterFromInput"
          @keydown.space="addToken"
          @keydown.delete="removeLastToken"
        >

        <!-- Submit Button -->
        <button
          class="button_search float-right"
          id="button_submit"
          ref="submitButton"
          :disabled="isEmpty()"
          @click="collectToken()"
          type="submit"
        >
          <img style="width: 24px;" :src="logoUrl" alt="Logo OMA icon">
        </button>
      </div>

      <!-- Error Message -->
      <div style="display: flex" v-show="showError">
        <small style="color: red; margin-right: auto;">{{ errorMessage }}</small>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

// Props
const props = defineProps({
  uniqueId: {
    type: String,
    required: true
  },
  multiline: {
    type: Boolean,
    default: false
  },
  xrefOrder: {
    type: Array,
    default: () => []
  },
  searchUrl: {
    type: String,
    default: '/oma/search/token/'
  },
  apiUrl: {
    type: String,
    default: '/api/xref/'
  },
  csrfToken: {
    type: String,
    default: ''
  },
  logoUrl: {
    type: String,
    default: '/static/image/logo-oma-o.svg'
  }
})

// Reactive state
const tokens = ref([])
const showError = ref(false)
const errorMessage = ref('Error.')
const postQuery = ref('')
const placeholder = ref('proteinid:P53_RAT | "Blue-light photoreceptor" | species:"Drosophila melanogaster"')

// Refs
const inputHandle = ref(null)
const submitButton = ref(null)

// Constants
const prefixes = {
  'Protein': ['proteinid', 'xref', 'go', 'ec', 'description', 'domain', 'sequence'],
  'Taxon': ['species', 'taxid', 'taxon'],
  'HOG': ['hog', 'sequence'],
  'OMA_Group': ['og', 'fingerprint', 'sequence'],
}
const defaultPrefix = 'description'
const wildCard = 'sequence'

// Methods
function getListPrefixes(lowercase = false) {
  let lp = [].concat(...Object.values(prefixes))
  if (lowercase) {
    lp = lp.map(element => element.toLowerCase())
  }
  return lp
}

function getPrefixUsed() {
  return tokens.value.map(x => getTypePrefix(x.prefix))
}

function getTypePrefix(prefix) {
  for (const key in prefixes) {
    if (Object.prototype.hasOwnProperty.call(prefixes, key)) {
      if (prefixes[key].includes(prefix.toLowerCase())) {
        return key
      }
    }
  }
  return null
}

function addToken(event) {
  event.preventDefault()
  let val = event.target.value.trim()

  if (val.length === 0 && tokens.value.length > 0) {
    collectToken()
    return
  }

  const singleTerm = val[0] !== '"'
  let multiTermClosed = val.length > 1 && val[val.length - 1] === '"'
  const hasPrefix = val.includes(':')
  const prefixEnd = val[val.length - 1] === ':'
  let p = hasPrefix ? val.split(':')[0].toLowerCase() : defaultPrefix

  // If prefix but not valid
  if (hasPrefix && !getListPrefixes(true).includes(p.toLowerCase())) {
    showError.value = true
    errorMessage.value = 'Error: Incorrect prefix.'
    return
  } else {
    showError.value = false
  }

  // If something typed
  if (val.length > 0) {
    // Multiple word query
    if (!singleTerm) {
      // STOP if multiple not closed
      if (!multiTermClosed) {
        if (event.code === 'Space') {
          event.target.value = val + ' '
        }
        return
      }
    }

    // STOP if the prefix is fine and we are at :
    if (prefixEnd) {
      return
    }

    // has a prefix
    if (hasPrefix) {
      let tmp = val.split(':')[1].trim()
      const tmpSingleTerm = tmp[0] !== '"'
      const tmpMultiTermClosed = val.length > 1 && tmp[tmp.length - 1] === '"'

      // multiple term
      if (!tmpSingleTerm) {
        // STOP if not closed
        if (!tmpMultiTermClosed) {
          if (event.code === 'Space') {
            event.target.value = val + ' '
          }
          return
        }
      }
      val = tmp
    }

    if (validateToken(val.replaceAll('"', ''), singleTerm, p)) {
      val = val.replaceAll('"', '')
      tokens.value.push({
        query: val,
        single_term: singleTerm,
        prefix: p,
        type: getTypePrefix(p)
      })
      event.target.value = ''
    }
  }

  // Scroll token container to the right
  const tokenContainer = document.getElementById(`token-container_${props.uniqueId}`)
  if (tokenContainer) {
    tokenContainer.scrollLeft += 200000
  }
}

function addTokenAndSearch(event) {
  addToken(event)
  if (tokens.value.length > 0) {
    collectToken()
    submitButton.value?.click()
  }
}

function removeToken(index) {
  tokens.value.splice(index, 1)
}

function removeLastToken(event) {
  if (event.target.value.length === 0) {
    removeToken(tokens.value.length - 1)
  }
}

function enterFromInput(event) {
  if (event.target.value.trim().length > 0) {
    addToken(event)
  } else {
    event.target.nextElementSibling?.focus()?.click()
  }
}

function collectToken() {
  postQuery.value = JSON.stringify(tokens.value)
}

function detokenize(index) {
  const token = tokens.value.splice(index, 1)[0]
  const inputTokenSearch = document.getElementById(`input_token_search_${props.uniqueId}`)

  let tokenStr = token.prefix + ': '
  tokenStr += token.single_term ? '' : '"'
  tokenStr += token.query
  tokenStr += token.single_term ? '' : '"'

  if (inputTokenSearch) {
    inputTokenSearch.value = tokenStr
  }
}

function onChangePrefix(target, t) {
  const prefix = target.value

  if (validateToken(t.query, t.single_term, prefix, true)) {
    t.prefix = prefix.toLowerCase()
  } else {
    target.value = t.prefix
  }
}

function validateToken(val, singleTerm, p, onChange = false) {
  if (wildCard.includes(p)) {
    return true
  }

  // validate prefix not in conflict with other prefix
  const pu = getPrefixUsed()
  const currentPrefixType = getTypePrefix(p)

  if (currentPrefixType !== 'Taxon') {
    const noTaxon = pu.filter(x => x !== 'Taxon')

    if (noTaxon.length === 0) {
      return true
    } else if (onChange && noTaxon.length === 1) {
      return true
    } else if (noTaxon.length > 0 && noTaxon.includes(currentPrefixType)) {
      return true
    } else if (noTaxon.length > 0 && !noTaxon.includes(currentPrefixType)) {
      showError.value = true
      errorMessage.value = `Warning: You are searching for ${noTaxon[0]}; you can't add a token for ${currentPrefixType}`
      return false
    }
  }

  return true
}

function preloadToken(newTokens) {
  tokens.value = []
  for (const token of newTokens) {
    if (validateToken(token.query, token.single_term, token.prefix)) {
      tokens.value.push({
        query: token.query,
        single_term: token.single_term,
        prefix: token.prefix,
        type: token.type
      })
    }
  }
  placeholder.value = ''
  inputHandle.value?.focus()
}

function isEmpty() {
  return tokens.value.length === 0
}

function modalClicked() {
  // Use Bootstrap's modal API
  const modal = document.getElementById(`exampleModal_${props.uniqueId}`)
  if (modal && typeof $ !== 'undefined') {
    $(`#exampleModal_${props.uniqueId}`).modal('show')
  }
}

function formatTokenString(str) {
  if (str.length < 20) {
    return str
  }
  return str.slice(0, 20) + '...'
}

// Setup autocomplete on mount
onMounted(() => {
  // jQuery Autocomplete setup (if jQuery is available)
  if (typeof $ !== 'undefined' && $.fn.autocomplete) {
    const autocompleteOpts = {
      paramName: 'search',
      serviceUrl: props.apiUrl,
      minChars: 3,
      triggerSelectOnValidInput: false,
      deferRequestBy: 200,
      transformResult: function (response) {
        const json = JSON.parse(response)
        json.sort(function (a, b) {
          const idxA = props.xrefOrder.indexOf(a.source)
          const idxB = props.xrefOrder.indexOf(b.source)
          if (idxA === idxB) {
            return a.xref > b.xref ? 1 : -1
          }
          return idxA - idxB
        })
        return {
          suggestions: $.map(json, function (dataItem) {
            return { value: dataItem.xref, data: dataItem }
          })
        }
      },
      groupBy: 'source',
      formatResult: function (suggestion, currentValue) {
        if (!currentValue) {
          return suggestion.value
        }
        const pattern = '(' + currentValue.replace(/[|\\{}()[\]^$+*?.]/g, '\\$&') + ')'
        const highlightAndEscape = function (val) {
          return val.replace(new RegExp(pattern, 'gi'), '<strong>$1</strong>')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/&lt;(\/?strong)&gt;/g, '<$1>')
        }
        return '<span class="auto-xref">' + highlightAndEscape(suggestion.data.xref) + '</span> &nbsp;' +
          '<span class="auto-omaid">' + suggestion.data.omaid + '</span>' +
          '<span class="auto-species">' + highlightAndEscape(suggestion.data.genome.species) + '</span>'
      },
      onSelect: function (item) {
        window.location.href = '/oma/vps/' + item.data.entry_nr
        return false
      }
    }
    $(`#input_token_search_${props.uniqueId}`).autocomplete(autocompleteOpts)
  }
})

// Expose methods for external use (Django templates)
defineExpose({
  preloadToken,
  addToken,
  addTokenAndSearch,
  removeToken,
  collectToken,
  isEmpty
})
</script>

<style scoped>
.button_search {
  cursor: pointer;
  align-self: center;
  height: 100%;
  background-color: transparent;
  border: none;
  margin-right: 4px;
  margin-left: auto;
  order: 2;
}

.button_search:disabled {
  cursor: not-allowed;
}

.help_icon {
  align-self: center;
  font-size: 1.5em;
  margin: 4px;
  cursor: pointer;
}

.prefix-dropdown {
  border: none;
  background-color: transparent;
}

.vl {
  border-left: 2px solid grey;
  margin-left: 4px;
  margin-right: 4px;
}

.search-input-container {
  display: flex;
  border: 1px solid #eee;
  font-size: 0.9em;
  box-sizing: border-box;
  padding: 0 0 0 4px;
  border-radius: 500px;
}

.ml-input {}

.sl-input {
  height: 50px;
}

.token-input__tag {
  height: 30px;
  display: inline-block;
  margin-right: 10px;
  background-color: #eee;
  margin-top: 10px;
  line-height: 30px;
  padding: 0 5px;
  border-radius: 5px;
}

.token-input__tag > span {
  cursor: pointer;
  opacity: 0.75;
}

.token-input__text {
  border: none;
  outline: none;
  font-size: 0.9em;
  line-height: 50px;
  flex-grow: 1;
  background: transparent;
}

.token-delete {
  margin-left: 4px;
  color: red;
}

.token-container {
  overflow: scroll;
  display: inline;
}

.ml-token-con {
  margin-bottom: 8px;
}

.sl-token-con {
  white-space: nowrap;
}
</style>
