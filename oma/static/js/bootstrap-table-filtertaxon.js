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

    var showAvdSearch = function (pColumns, searchTitle, searchText, that) {

        if (!$("#avdSearchModal" + "_" + that.options.idTable).hasClass("modal")) {
            var vModal = sprintf("<div id=\"avdSearchModal%s\"  class=\"modal fade\" tabindex=\"-1\" role=\"dialog\" aria-labelledby=\"mySmallModalLabel\" aria-hidden=\"true\">", "_" + that.options.idTable);
            vModal += "<div class=\"modal-dialog modal-lg\">";
            vModal += " <div class=\"modal-content\">";
            vModal += "  <div class=\"modal-header\">";
            vModal += "   <button type=\"button\" class=\"close\" data-dismiss=\"modal\" aria-hidden=\"true\" >&times;</button>";
            vModal += sprintf('   <h4 class=\"modal-title\">%s </h4>  <a class="" id="reset_tree" > Click here to reset tree selection.</a> ', searchTitle);
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
            init_phyloIo(that);

            jmodal.append(sprintf('<button type="button" id="btnCloseAvd%s" class="btn btn-default pull-right" >%s</button>', "_" + that.options.idTable, searchText));

            $("#btnCloseAvd" + "_" + that.options.idTable).click(function () {
                that.onColumntaxonFilter('custom');
                $("#avdSearchModal" + "_" + that.options.idTable).modal('hide');
            });

            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        } else {
            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        }
    };

    var init_phyloIo = function (that) {

        var treecomp;
        var maxGenome = 1000000;
        var mouse = {x: 0, y: 0};
        document.addEventListener('mousemove', function (e) {
            mouse.x = e.clientX || e.pageX;
            mouse.y = e.clientY || e.pageY
        }, false);
        var svg_cont = $('#container_phylo');
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
                            that.tax_converter['custom'] = exportList;
                            localStorage.setItem('custom_taxon_filter', JSON.stringify(exportList));
                            that.onColumntaxonFilter('custom');
                        }
                    ]
                };
                // INIT THE PHYLO.IO
                treecomp = TreeCompare().init({
                    maxNumGenome: maxGenome,
                    nodeFunc: additionalNodeFunctions
                });
                var tree1 = treecomp.addTree(newick, undefined);
                // SET UP THE PHYLO.IO
                treecomp.changeCanvasSettings({
                    autoCollapse: tree1.data.autoCollapseDepth,
                    enableScale: false
                });
                // RENDER THE PHYLO.IO
                treecomp.viewTree(tree1.name, "container_phylo");

                // SELECT NODES IN CUSTOM SELECTION FILTER
                for (var i = 0; i < tree1.root.leaves.length; i++) {
                    if (that.tax_converter['custom'].indexOf(tree1.root.leaves[i].name) !== -1) {
                        treecomp.selectAllSpecies(tree1.root.leaves[i], tree1, maxGenome, true);
                    }
                }

                // RESET THE FILTERING
                $("#reset_tree").click(function () {

                    /*

                    for (var i = 0; i < tree1.root.leaves.length; i++) {
                        if (tree1.root.leaves[i].selectForOMAExport){
                            treecomp.unselect(tree1.root.leaves[i]);
                            }
                    }

                    treecomp.update(tree1.root, tree1.data);
                    treecomp.exportList = []

                    */


                    that.tax_converter['custom'] = [];
                    localStorage.setItem('custom_taxon_filter', JSON.stringify([]));
                    that.onColumntaxonFilter('custom');
                    console.log(that.tax_converter['custom'],treecomp.exportList );



                });
            },
            dataType: "text"
        });


    }

    var add_phyloioDOM = function () {
        var htmlPhylo = [];
        htmlPhylo.push('<div class="container-fluid">');
        htmlPhylo.push('<div class="row">');
        htmlPhylo.push('<div class="col-md-12">');
        htmlPhylo.push('<div class="" id="container_phylo" style="width: 100%;">');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        htmlPhylo.push('</div>');
        return htmlPhylo;
    }

    $.extend($.fn.bootstrapTable.defaults, {
        taxonFilter: false,
        idForm: 'taxonFilter',
        actionForm: '',
        idTable: undefined,
        urlSpecieTree: undefined,
        onColumntaxonFilter: function (field, text) {
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
            return [];
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

        if (!this.options.idTable) {
            return;
        }

        if (!this.options.urlSpecieTree) {
            return;
        }

        // List of inputted taxon name (not checked vor validity)
        this.list_taxon_accepted = this.options.taxon_to_show();

        // SEARCH MODE TYPE
        this.multi_species_search = false;

        // INPUTTED TAXON NAME WITH THEY SPECIES LIST (CHECK FOR VALIDITY)
        this.tax_converter = build_tax_to_species_converter(this.options.urlSpecieTree, this.list_taxon_accepted);

        // ADD CUSTOM FILTERING FROM LOCAL STORAGE
        var local_custom = localStorage.getItem('custom_taxon_filter');
        this.tax_converter['custom'] = (local_custom === null) ? [] : JSON.parse(local_custom);

        var that = this,
            html = [];

        //  ADD DROPDOWN MENU
        html.push(sprintf('<div class="dropdown columns columns-%s btn-group pull-%s" role="group">', this.options.buttonsAlign, this.options.buttonsAlign));
        html.push(sprintf('<button class="btn btn-default%s dropdown-toggle' + '" type="button" name="taxonFilter" aria-label="advanced search" title="%s" data-toggle="dropdown">', that.options.iconSize === undefined ? '' : ' btn-' + that.options.iconSize, that.options.formattaxonFilter()));
        html.push(sprintf('<i class="%s %s"></i>', that.options.iconsPrefix, that.options.icons.taxonFilterIcon));
        html.push('<span class="caret"></span>');
        html.push('</button>');
        html.push('<ul class="dropdown-menu">');

        //  ADD LI FOR ALL
        html.push(' <li><a  class="li_filtertax"  id="all">All</a></li> ');

        //  ADD LI FOR EACH DESIRED TAXA
        for (var tax in this.tax_converter) {
            if (tax !== 'custom') {

                html.push(' <li><a  class="li_filtertax" id="' + tax + '">' + tax + '</a></li> ');
            }
        }

        // ADD SEPARATOR AND LI FOR CUSTOM
        html.push(' <li class="divider"></li> ');
        html.push(' <li><a  class="li_filtertax"  id="custom">Custom  <span class="glyphicon glyphicon-pencil pull-right"  id="custom_icon" aria-hidden="true"></span> </a> </li> ');

        html.push(' </ul>');
        html.push('</div>');

        that.$toolbar.prepend(html.join(''));

        //  ADD LI CLICK ACTION
        that.$toolbar.find('a[class="li_filtertax"]')
            .off('click').on('click', function (event) {

            if (this.id === 'custom') {
                showAvdSearch(that.columns, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);
            }
            else {
                that.onColumntaxonFilter($(event.currentTarget)[0].id);
            }
        });

        //  ADD RESET BUTTON ACTION
        d3.select("#reset_taxon_filter").on('click', function () {
            //that.resetSearch();
            that.onColumntaxonFilter('all');
        })

    };

    BootstrapTable.prototype.load = function (data) {
        _load.apply(this, Array.prototype.slice.apply(arguments));

        if (!this.options.taxonFilter) {
            return;
        }

        if (typeof this.options.idTable === 'undefined') {
            return;
        } else if (typeof this.options.urlSpecieTree === 'undefined') {
            return;
        }
        else {
            if (!firstLoad) {

                var height = parseInt($(".bootstrap-table").height());
                height += 10;
                $("#" + this.options.idTable).bootstrapTable("resetView", {height: height});
                firstLoad = true;
            }
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

                var lsp = that.tax_converter[that.multi_species_search];

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
