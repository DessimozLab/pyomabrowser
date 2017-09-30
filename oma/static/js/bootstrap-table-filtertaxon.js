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

        if (!$("#avdSearchModal" + "_" + that.options.idTable).hasClass("modal")) {

            var vModal = sprintf("<div id=\"avdSearchModal%s\"  class=\"modal fade\" tabindex=\"-1\" role=\"dialog\" aria-labelledby=\"mySmallModalLabel\" aria-hidden=\"true\">", "_" + that.options.idTable);
            vModal += "<div class=\"modal-dialog modal-lg\">";
            vModal += " <div class=\"modal-content\">";
            vModal += "  <div class=\"modal-header\">";
            vModal += "   <button type=\"button\" class=\"close\" data-dismiss=\"modal\" aria-hidden=\"true\" >&times;</button>";
            vModal += sprintf('  <h4 class=\"modal-title\"><b>Custom filter:</b> <a href="#" id="username" data-type="text" data-url="" data-pk="1"  data-title="Enter username">%s</a> <small>(click on text field to rename this filter)</small> </h4>   ', custom_item.name);
            vModal += '<a class="" id="reset_tree" > Click here to reset the tree selection.</a> <br>';
            vModal += '<a class="" id="delete_tree" > Click here to delete this custom filter.</a>';
            vModal += "  </div>";
            vModal += "  <div class=\"modal-body modal-body-custom\">";
            vModal += sprintf("   <div class=\"container-fluid\" id=\"avdSearchModalContent%s\" style=\"padding-right: 0px;padding-left: 0px;\" >", "_" + that.options.idTable);
            vModal += "   </div>";
            vModal += "  </div>";
            vModal += "  </div>";
            vModal += " </div>";
            vModal += "</div>";

            $("body").append($(vModal));

            // ADD PHYLO.IO DOM ELEMENT
            var phyloContent = add_phyloioDOM(), jmodal = $('#avdSearchModalContent' + "_" + that.options.idTable);

            jmodal.append(phyloContent.join(''));

            // SETUP PHYLO.IO
            that.item_to_update = custom_item;
            init_phyloIo(that);
            that.custom_filter_search = true;
            that.onColumntaxonFilter(that.item_to_update.Uid);

            jmodal.append(sprintf('<button type="button" id="btnCloseAvd%s" class="btn btn-default pull-right" >%s</button>', "_" + that.options.idTable, searchText));

            $("#btnCloseAvd" + "_" + that.options.idTable).click(function () {
                that.custom_filter_search = true;
                that.onColumntaxonFilter(that.item_to_update.Uid);
                $("#avdSearchModal" + "_" + that.options.idTable).modal('hide');
            });

            $('#username').editable();

            $('#username').on('save', function(e, params) {
                that.item_to_update.name = params.newValue;
                localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));
                var span = $('#li_custom_' + that.item_to_update.Uid).find('span[class="spanli"]')[0];
                span.textContent = that.item_to_update.name;
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
                document.getElementById('li_custom_' + that.item_to_update.Uid).parentElement.remove();

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
            url: that.options.urlSpecieTree,
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

     // EXTENSION OF BOOTSTRAPTABLE LIB

    $.extend($.fn.bootstrapTable.defaults, {
        taxonFilter: false,
        idTable: 'taxonFilter',
        urlSpecieTree: undefined,
        onColumntaxonFilter: function (name_selector) {
            return false;
        }
    });

    $.extend($.fn.bootstrapTable.defaults.icons, {
        taxonFilterIcon: 'glyphicon-filter'
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
            return ['Vertebrata', 'Mammalia', 'Neoptera', 'Viridiplantae', 'Fungi'];
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

        if (!this.options.urlSpecieTree) {
            return;
        }

        // List of inputted taxon name (not checked vor validity)
        this.list_taxon_accepted = this.options.taxon_to_show();

        // SEARCH MODE TYPE
        this.multi_species_search = false;
        this.custom_filter_search = false;

        // INPUTTED TAXON NAME WITH THEY SPECIES LIST (CHECK FOR VALIDITY)
        this.tax_converter = build_tax_to_species_converter(this.options.urlSpecieTree, this.list_taxon_accepted);

        // ADD CUSTOM FILTERING FROM LOCAL STORAGE
        var local_custom = localStorage.getItem('custom_taxon_filter');
        this.tax_converter['custom'] = (JSON.parse(local_custom) === null) ? [] : JSON.parse(local_custom);

        var that = this,
            html = [];

        //  ADD DROPDOWN MENU
        html.push(sprintf('<div class="dropdown columns columns-%s btn-group pull-%s" role="group">', this.options.buttonsAlign, this.options.buttonsAlign));
        html.push(sprintf('<button class="btn btn-default%s dropdown-toggle' + '" type="button" name="taxonFilter" aria-label="advanced search" title="%s" data-toggle="dropdown">', that.options.iconSize === undefined ? '' : ' btn-' + that.options.iconSize, that.options.formattaxonFilter()));
        html.push(sprintf('<i class="%s %s"></i>', that.options.iconsPrefix, that.options.icons.taxonFilterIcon));
        html.push('<span class="caret"></span>');
        html.push('</button>');
        html.push('<ul class="dropdown-menu" id="ul_custom" >');

        //  ADD LI FOR ALL
        html.push('<li role="presentation" class="dropdown-header li_filter">DEFAULT</li>');
        html.push(' <li><a  class="li_filtertax"  id="all">&emsp; All <span id="li_ok_all" class="glyphicon glyphicon-ok pull-right" aria-hidden="true"></span> </a></li> ');

        //  ADD LI FOR EACH DESIRED TAXA
        for (var tax in this.tax_converter) {
            if (tax !== 'custom') {
                html.push(' <li><a  class="li_filtertax_default" id="' + tax + '"> &emsp; ' + tax + ' <span id="li_ok_' + tax + '" class="glyphicon glyphicon-ok pull-right hidden" aria-hidden="true"></span> </a></li> ');
            }
        }

        // ADD SEPARATOR AND LI FOR CUSTOM
        html.push(' <li class="divider"></li> ');
        html.push('<li role="presentation" class="dropdown-header li_filter">CUSTOM</li>');

        //  ADD LI FOR EACH CUSTOM FILTER
        for (var tax in this.tax_converter['custom']) {
            var custom_item = this.tax_converter['custom'][tax];
            html.push(' <li><a  class="li_filtertax_custom" id="li_custom_' + custom_item.Uid + '">&emsp;  <span class="spanli">' + custom_item.name + ' </span> <span id="li_ok_' + custom_item.Uid + '" class="glyphicon glyphicon-ok pull-right hidden" aria-hidden="true"></span> </a></li> ')
        }
        html.push(' <li><a  class="li_filtertax"  id="li_add"> <h6 id="li_h6_add">Add custom filter</h6> </a> </li> ');
        html.push(' </ul>');
        html.push('</div>');

        that.$toolbar.prepend(html.join(''));

        //  ADD LI CLICK ACTION
        that.$toolbar.find('a[class="li_filtertax_default"]')
            .off('click').on('click', function (event) {

            $('[id^="li_ok_"]').toggleClass('hidden', true);
            $(this).find("span").toggleClass('hidden', false);
            that.onColumntaxonFilter($(event.currentTarget)[0].id);

        });

        that.$toolbar.find('a[class="li_filtertax_custom"]')
            .off('click').on('click', function (event) {

            // HIDE ALL OK ICON ON LI
            $('[id^="li_ok_"]').toggleClass('hidden', true);

            // GET THE RELATED CUSTOM ITEM
            var liid = $(this)[0].id.replace(/^li_custom_/, '');
            var ci = get_item_by_id(that.tax_converter['custom'], liid, 'Uid');

            // SHOW OK ICON FOR THIS LI
            $(this).find('[id^="li_ok_"]').toggleClass('hidden', false);

            showAvdSearch(ci, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);
        });

        //  ADD RESET BUTTON ACTION
        d3.select("#reset_taxon_filter").on('click', function () {
            $('[id^="li_ok_"]').toggleClass('hidden', true);
            $('[id^="li_ok_all"]').toggleClass('hidden', false);
            that.onColumntaxonFilter('all');
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
            var empty_filter = {Uid: idMax, name: 'Unname Item', lsp: []};
            that.tax_converter['custom'].push(empty_filter);
            localStorage.setItem('custom_taxon_filter', JSON.stringify(that.tax_converter['custom']));

            // add the li in the list after last customfilter li
            var custom_ul = document.getElementById("ul_custom");
            var lis = custom_ul.getElementsByTagName("li");
            var li_add = lis[lis.length - 1];

            var new_item = document.createElement('li');
            new_item.innerHTML = ' <a  class="li_filtertax_custom" id="li_custom_' + empty_filter.Uid + '"> &emsp;  <span class="spanli">' + empty_filter.name + ' </span><span id="li_ok_' + empty_filter.Uid + '" class="glyphicon glyphicon-ok pull-right hidden" aria-hidden="true"></span> </a> ';

            custom_ul.insertBefore(new_item, li_add);

            // ADD CLICK EVENT TO NEWLY CREATED LI
            $(new_item).off('click').on('click', function () {

            // HIDE ALL OK ICON ON LI
            $('[id^="li_ok_"]').toggleClass('hidden', true);

            // GET THE RELATED CUSTOM ITEM
            var ci = get_item_by_id(that.tax_converter['custom'], empty_filter.Uid, 'Uid');

            // SHOW OK ICON FOR THIS LI
            $(new_item).find('[id^="li_ok_"]').toggleClass('hidden', false);

            showAvdSearch(ci, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);
        });

            // HIDE ALL OK ICON ON LI
            $('[id^="li_ok_"]').toggleClass('hidden', true);
            // SHOW OK ICON FOR THIS LI
            $(new_item).find('[id^="li_ok_"]').toggleClass('hidden', false);


            // launch the modal
            showAvdSearch(empty_filter, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);

        });

        //turn EDITABLE FIELD to inline mode
        $.fn.editable.defaults.mode = 'inline';

    };

    BootstrapTable.prototype.load = function (data) {
        _load.apply(this, Array.prototype.slice.apply(arguments));

        if (!this.options.taxonFilter) {
            return;
        }

        if (!this.options.urlSpecieTree) {
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
                        return obj.Uid === that.multi_species_search;
                    });
                    lsp = result[0].lsp;
                }
                else {
                    lsp = that.tax_converter[that.multi_species_search];
                }


                for (var sp in lsp) {

                    var fval = lsp[sp].toLowerCase();
                    var value = item['taxon'];

                    value = value.species.toLowerCase();

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
        var data = this.options.data;

        if (this.multi_species_search || this.searchText || this.options.sortName || !$.isEmptyObject(this.filterColumns) || !$.isEmptyObject(this.filterColumnsPartial)) {
            data = this.data;
        }

        if (useCurrentPage) {
            return data.slice(this.pageFrom - 1, this.pageTo);
        }

        return data;
    };


}(jQuery);