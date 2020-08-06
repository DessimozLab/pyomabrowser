/**
 * @author: aperez <aperez@datadec.es>
 * @version: v2.0.0
 *
 * @update Dennis Hernández <http://djhvscf.github.io/Blog>
 *
 * @update Clement Train
 */



!function ($) {
    'use strict';

    var firstLoad = false;

    var sprintf = $.fn.bootstrapTable.utils.sprintf;

    var container_filter_taxon = $("#filter-taxon-container");

    var that;


    // HELPER FUNCTIONS

    var get_item_by_id = function(array, value, type){

            var result = array.filter(function (obj) {
                return obj[type] == value;
            });

             if (result.length !== 1){
                 console.log('BUG: get_item_by_id should return one and only one element. Here it returned: ', result);
             }

             return result[0]

    }

    var build_tax_to_species_converter = function (url_tree, list_taxons) {

        var converter = {};

        $.ajaxSetup({
            async: false
        });

        $.getJSON(url_tree, function (json) {
            var tree_vis = tnt.tree().data(json);

            var root = tree_vis.root();

            for (var e in list_taxons) {

                var node = root.find_node_by_name(list_taxons[e]);

                if (node) {
                    var leaves = node.get_all_leaves();

                    if (leaves) {

                        converter[list_taxons[e]] = [];

                        for (var i in leaves) {

                            converter[list_taxons[e]].push(leaves[i].node_name());

                        }


                    }

                }
            }

        });

        $.ajaxSetup({
            async: true
        });


        return converter

    };

    var showAvdSearch = function (custom_item, searchTitle, searchText, that) {

        if (!$("#avdSearchModal_" + that.options.idTable).hasClass("modal")) {

            var modal_html = [] ;

            modal_html.push(' <div id="avdSearchModal_'+that.options.idTable+'" class="modal fade bd-example-modal-lg" tabindex="-1" role="dialog" aria-labelledby="mySmallModalLabel" aria-hidden="true">');
            modal_html.push('<div class="modal-dialog modal-lg">');
            modal_html.push('<div class="modal-content">');

            // HEADER
            modal_html.push('<div class="modal-header">');
            modal_html.push('<h4 class="modal-title"><b>Custom filter:</b> <a href="#" id="username" data-type="text" data-url="" data-pk="1"  data-title="Enter username">'+custom_item.name+'</a> <small>(click to rename)</small> </h4>  <br>  ');
            modal_html.push('</div>');

            // CONTENT
            modal_html.push('<div class="modal-body modal-body-custom">');
            modal_html.push(sprintf("   <div class=\"container-fluid\" id=\"avdSearchModalContent%s\" style=\"padding-right: 0px;padding-left: 0px;\" >", "_" + that.options.idTable));
            modal_html.push('</div>');
            modal_html.push('</div>');
            modal_html.push('</div>');
            modal_html.push('</div>');
            modal_html.push('</div>');


            $('body').append(modal_html.join(''));

            // ADD PHYLO.IO DOM ELEMENT
            var phyloContent = add_phyloioDOM(), jmodal = $('#avdSearchModalContent_' + that.options.idTable);

            jmodal.append(phyloContent.join(''));

            // SETUP PHYLO.IO
            that.item_to_update = custom_item;
            init_phyloIo(that);
            that.custom_filter_search = true;
            that.onColumntaxonFilter(that.item_to_update.Uid);



             jmodal.append(sprintf('<button type="button" class="btn btn-outline-danger"  id="reset_tree" > Reset the tree selection</button> <span></span>'));
             jmodal.append(sprintf('<button type="button" class="btn btn-outline-danger"  id="delete_tree" > Delete the filter</button>'));

            jmodal.append(sprintf('<button type="button" id="btnCloseAvd%s" class="btn btn-primary float-right" >%s</button>', "_" + that.options.idTable, searchText));

            $("#btnCloseAvd" + "_" + that.options.idTable).click(function () {
                that.custom_filter_search = true;
                that.onColumntaxonFilter(that.item_to_update.Uid);
                $("#avdSearchModal" + "_" + that.options.idTable).modal('hide');
            });

            $('#username').editable({mode: 'inline',});

            $('#username').on('save', function(e, params) {
                that.item_to_update.name = params.newValue;
                localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));
                $('#custom_' + that.item_to_update.Uid)[0].nextSibling.textContent = that.item_to_update.name;

            });


            // REMOVE THIS CUSTOM FILTERING
            $("#delete_tree").click(function () {

                // REMOVE THE ITEM FROM CUSTOM
                var custom_cleaned = that.tax_converter['custom'].filter(function(el) {
                    return el.Uid !== that.item_to_update.Uid;
                });

                // UPDATE CUSTOM AND LOCAL STORAGE
                that.tax_converter['custom'] = custom_cleaned;
                localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));

                // REMOVE CORRESPONDING LI
                document.getElementById('custom_' + that.item_to_update.Uid).parentElement.remove();

                // RESET FILTERING
                that.item_to_update = null;
                that.onColumntaxonFilter('all');

                // CLOSE MODAL
                $("#avdSearchModal" + "_" + that.options.idTable).modal('hide');

            });

            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        }
        else {
            that.item_to_update = custom_item;
            $('#username').text(that.item_to_update.name);
            init_phyloIo(that);
            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        }
    };

    var init_phyloIo = function (that) {

        var phylo_con = document.getElementById("phylo_io");
        while (phylo_con.firstChild) {
            phylo_con.removeChild(phylo_con.firstChild);
        }

        var maxGenome = 1000000;
        var mouse = {x: 0, y: 0};
        document.addEventListener('mousemove', function (e) {
            mouse.x = e.clientX || e.pageX;
            mouse.y = e.clientY || e.pageY
        }, false);
        var svg_cont = $('#phylo_io');
        svg_cont.css('height', 480);
        svg_cont.scroll(function () {
            if ($('.tooltip')) {
                $('.tooltip').remove();
            }
        });

        //load the data from the Json file
        $.ajax({
            url: that.options.urlSpeciesTree,
            success: function (newick) {

                // DEFINED BEHAVIOR ON NODE SELECTION
                var additionalNodeFunctions = {
                    "selectForExport": [
                        function (exportList) {
                            that.item_to_update.lsp = exportList;
                            localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));
                            that.custom_filter_search = true;
                            that.onColumntaxonFilter(that.item_to_update.Uid);
                        }
                    ]
                };
                // INIT THE PHYLO.IO
                var treecomp = TreeCompare().init({
                    maxNumGenome: maxGenome,
                    nodeFunc: additionalNodeFunctions
                });
                var tree1 = treecomp.addTree(newick, undefined);
                // SET UP THE PHYLO.IO
                treecomp.changeCanvasSettings({
                    autoCollapse: tree1.data.autoCollapseDepth,
                    enableScale: false,
                });

                // RENDER THE PHYLO.IO
                treecomp.viewTree(tree1.name, "phylo_io");

                // SELECT NODES IN CUSTOM SELECTION FILTER
                for (var i = 0; i < tree1.root.leaves.length; i++) {
                    if (that.item_to_update.lsp.indexOf(tree1.root.leaves[i].name) !== -1) {
                        treecomp.selectAllSpecies(tree1.root.leaves[i], tree1, maxGenome, true);
                    }
                }

                // RESET THE FILTERING
                $("#reset_tree").click(function () {
                    treecomp.exportList = [];
                    tree1 = treecomp.addTree(newick, undefined);
                    treecomp.viewTree(tree1.name, "phylo_io");
                    that.item_to_update.lsp = [];
                    localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));
                    that.custom_filter_search = true;
                    that.onColumntaxonFilter(that.item_to_update.Uid);
                });


            },
            dataType: "text"
        });


    };

    var add_phyloioDOM = function () {
        var htmlPhylo = [];
        htmlPhylo.push('<div class="container-fluid">');
        htmlPhylo.push('<div class="row">');
        htmlPhylo.push('<div class="col-md-12">');
        htmlPhylo.push('<div class="" id="phylo_io" style="width: 100%;">');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        return htmlPhylo;
    }

    // UTILS FUNCTIONS

    var add_input_div= function( id_input, label_text, custom ){

        if (!custom){

        return '<div> <input type="radio" class="form-check-input checkbox_taxa" id="'+id_input+'" <label class="form-check-label" for="'+id_input+'">'+label_text+'</label> </div>';
        }

        else {
           return '<div> <input type="radio" class="form-check-input checkbox_taxa" id="custom_'+id_input+'" <label class="form-check-label" for="'+id_input+'">'+label_text+' <a href="javascript:void(0);" class="edit" id="edit_' + id_input + '">(edit)</a> </label> </div>';
        }
    };

    var click_input = function (event) {

                    var name_ ;

                    if ($(event.currentTarget)[0].id.startsWith('custom_')) {
                        that.custom_filter_search =true;

                        name_ = $(event.currentTarget)[0].id.replace("custom_", "")
                    }

                    else {
                        name_ = $(event.currentTarget)[0].id
                    }

                    container_filter_taxon.find('input').not(this).prop('checked', false);
                    that.onColumntaxonFilter(name_);
            }

    var click_edit = function (event) {

                    // GET THE RELATED CUSTOM ITEM
                    var liid = $(this)[0].id.replace(/^edit_/, '');
                    var ci = get_item_by_id(that.tax_converter['custom'], liid, 'Uid');
                    showAvdSearch(ci, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);
            }

     // EXTENSION OF BOOTSTRAPTABLE LIB

    $.extend($.fn.bootstrapTable.defaults, {
        taxonFilter: false,
        idTable: 'taxonFilter',
        urlSpeciesTree: undefined,
        onColumntaxonFilter: function (name_selector) {
            return false;
        }
    });

    $.extend($.fn.bootstrapTable.defaults.icons, {
        taxonFilterIcon: 'fa-filter'
    });

    $.extend($.fn.bootstrapTable.Constructor.EVENTS, {
        'column-taxon-filter.bs.table': 'onColumntaxonFilter'
    });

    $.extend($.fn.bootstrapTable.locales, {
        formattaxonFilter: function () {
            return 'Filter the tables with your custom species set';
        },
        formatAdvancedCloseButton: function () {
            return "Apply";
        },
        taxon_to_show: function () {
            //return ['Vertebrata', 'Mammalia', 'Neoptera', 'Viridiplantae', 'Fungi'];
            return ['Dikarya', 'Saccharomycetaceae', 'Fungi', 'Viridiplantae', 'Fungi', 'Ascomycota', 'Eukaryota'];
        }
    });

    $.extend($.fn.bootstrapTable.defaults, $.fn.bootstrapTable.locales);

    var BootstrapTable = $.fn.bootstrapTable.Constructor,
        _initToolbar = BootstrapTable.prototype.initToolbar,
        _load = BootstrapTable.prototype.load,
        _initSearch = BootstrapTable.prototype.initSearch;

    BootstrapTable.prototype.initToolbar = function () {
            _initToolbar.apply(this, Array.prototype.slice.apply(arguments));

            if (!this.options.search) {
                return;
            }

            if (!this.options.taxonFilter) {
                return;
            }

            if (!this.options.urlSpeciesTree) {
                return;
            }

            // List of inputted taxon name (not checked vor validity)
            this.list_taxon_accepted = this.options.taxon_to_show();

            // SEARCH MODE TYPE
            this.multi_species_search = false;
            this.custom_filter_search = false;

            // INPUTTED TAXON NAME WITH THEY SPECIES LIST (CHECK FOR VALIDITY)
            this.tax_converter = build_tax_to_species_converter(this.options.urlSpeciesTree, this.list_taxon_accepted);

            // ADD CUSTOM FILTERING FROM LOCAL STORAGE
            var local_custom = localStorage.getItem('custom_taxon_filter');
            this.tax_converter['custom'] = (JSON.parse(local_custom) === null) ? [] : JSON.parse(local_custom);

            that = this;
            var html = [];

            //  ADD CHECKBOX MENU

            html.push('<h5>Filter by Taxon:</h5>');
            html.push('<div class="form-check pl-4">');

            //  ADD CHECKBOX FOR EACH DEFAULT TAXA
             html.push(add_input_div( 'all', 'All Taxon', false ));

            for (var tax in this.tax_converter) {
                if (tax !== 'custom') {
                    html.push(add_input_div( tax, tax, false));
                }
            }

            //  ADD CHECKBOX FOR EACH CUSTOM TAXA
            for (var tax in this.tax_converter['custom']) {
                var custom_item = this.tax_converter['custom'][tax];
                html.push(add_input_div(custom_item.Uid, custom_item.name, true ));
            }


            html.push('<div id="div_add" class="text-center" ><button type="button" id="li_add" class="btn  ">Add custom filter</button> </div>');

            container_filter_taxon.html("");

            container_filter_taxon.prepend(html.join(''));
            container_filter_taxon.find('input[id=all]').prop('checked', true);

            //  ADD BOX  ACTION
            container_filter_taxon.find('input')
                .off('click').on('click', click_input );

            // ADD EDIT CUSTOM ACTION
            container_filter_taxon.find('a[class=edit]')
                .off('click').on('click', click_edit );

            //  ADD RESET BUTTON ACTION
            d3.select("#reset_taxon_filter").on('click', function () {
                container_filter_taxon.find('input').prop('checked', false);
                that.onColumntaxonFilter('all');
                container_filter_taxon.find('input[id=all]').prop('checked', true);
            })

            //  ADD NEW CUSTOM FILTER
            d3.select("#li_add").on('click', function () {

                // create new object in the local storage
                // FIND THE GREATER UID AND ADD PLUS ONE FOR NEW UNIQUE ID
                var idMax = (that.tax_converter['custom'].length <= 0) ? 0 : that.tax_converter['custom'].reduce(function (l, e) {
                    return e.Uid > l.Uid ? e : l;
                }).Uid;
                idMax = idMax + 1;

                // INITIATE EMPTY CUSTOM FILTER INTO CUSTOM AND UPDATE LOCAL STORAGE
                var empty_filter = {Uid: idMax, name: 'Unnamed Item', lsp: []};
                that.tax_converter['custom'].push(empty_filter);
                localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));

                // add the new item after last customfilter
                var new_item = document.createElement('div');
                new_item.innerHTML = ' <input type="radio" class="form-check-input checkbox_taxa" id="custom_' + empty_filter.Uid + '" <label class="form-check-label" for="custom_' + empty_filter.Uid + '">' + empty_filter.name + ' <a href="javascript:void(0);" class="edit" id="edit_' + empty_filter.Uid + '"> (edit)</a></label>';

                $(new_item).insertBefore($("#div_add")[0]);

                // ADD CLICK EVENT TO NEWLY CREATED LI
                $(new_item).off('click').on('click', click_input);

                // ADD EDIT CUSTOM ACTION
                $(new_item).find('a[class=edit]').off('click').on('click', click_edit);

                $(new_item).trigger( "click");

                var ci = get_item_by_id(that.tax_converter['custom'], empty_filter.Uid, 'Uid');
                showAvdSearch(ci, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);

                });

        };

    BootstrapTable.prototype.load = function (data) {
        _load.apply(this, Array.prototype.slice.apply(arguments));

        if (!this.options.taxonFilter) {
            return;
        }

        if (!this.options.urlSpeciesTree) {
            return;
        }

        if (!firstLoad) {
            var height = parseInt($(".bootstrap-table").height());
            height += 10;
            $("#" + this.options.idTable).bootstrapTable("resetView", {height: height});
            firstLoad = true;
        }
    };

    BootstrapTable.prototype.initSearch = function () {

        _initSearch.apply(this, Array.prototype.slice.apply(arguments));

        if (!this.options.taxonFilter) {
            return;
        }

        if (this.multi_species_search && this.multi_species_search !== 'all') {
            var that = this;


            this.data = $.grep(this.data, function (item, i) {

                var lsp;

                if (that.custom_filter_search) {
                    var result = that.tax_converter['custom'].filter(function (obj) {
                        return obj.Uid == that.multi_species_search;
                    });

                    lsp = result[0].lsp;

                }
                else {
                    lsp = that.tax_converter[that.multi_species_search];
                }


                for (var sp in lsp) {

                    var fval = lsp[sp].toLowerCase();
                    var value = item['taxon'];
                    value = (value.species + value.strain).toLowerCase();

                    if ($.inArray('taxon', that.header.fields) !== -1 &&
                        (typeof value === 'string' || typeof value === 'number') &&
                        (value === fval)) {
                        return true;
                    }

                }
                return false;
            })


        }

        if (this.multi_species_search && this.multi_species_search !== 'all' || this.options.searchText) {
            $('.alert_remove').show();
        }
        else {
            $('.alert_remove').hide();
        }

    };

    BootstrapTable.prototype.onColumntaxonFilter = function (name_selector) {
        this.resetSearch('');
        this.multi_species_search = name_selector;
        this.options.pageNumber = 1;
        this.initSearch();
        this.updatePagination();
        this.trigger('column-taxon-filter', 'arg1', 'arg2');
        this.multi_species_search = false;
        this.custom_filter_search = false;
    };

    BootstrapTable.prototype.getData = function (useCurrentPage) {

        if (useCurrentPage) {
            return this.data.slice(this.pageFrom - 1, this.pageTo);
        }

        return this.data;
    };


}(jQuery);