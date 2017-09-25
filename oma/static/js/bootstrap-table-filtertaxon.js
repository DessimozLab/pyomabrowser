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

    var build_tax_to_species_converter = function(url_tree, list_taxons){

        var converter = {};

        $.ajaxSetup({
    async: false
});

        $.getJSON(url_tree, function(json) {
            var tree_vis = tnt.tree().data(json);

            var root = tree_vis.root();

            for (var e in list_taxons){

                var node = root.find_node_by_name(list_taxons[e]);

                if (node){
                    var leaves = node.get_all_leaves();

                    if (leaves) {

                        converter[list_taxons[e]] = [];

                        for (var i in leaves){

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

    /*

    var showAvdSearch = function (pColumns, searchTitle, searchText, that) {

        if (!$("#avdSearchModal" + "_" + that.options.idTable).hasClass("modal")) {
            var vModal = sprintf("<div id=\"avdSearchModal%s\"  class=\"modal fade\" tabindex=\"-1\" role=\"dialog\" aria-labelledby=\"mySmallModalLabel\" aria-hidden=\"true\">", "_" + that.options.idTable);
            vModal += "<div class=\"modal-dialog modal-xs\">";
            vModal += " <div class=\"modal-content\">";
            vModal += "  <div class=\"modal-header\">";
            vModal += "   <button type=\"button\" class=\"close\" data-dismiss=\"modal\" aria-hidden=\"true\" >&times;</button>";
            vModal += sprintf("   <h4 class=\"modal-title\">%s</h4>", searchTitle);
            vModal += "  </div>";
            vModal += "  <div class=\"modal-body modal-body-custom\">";
            vModal += sprintf("   <div class=\"container-fluid\" id=\"avdSearchModalContent%s\" style=\"padding-right: 0px;padding-left: 0px;\" >", "_" + that.options.idTable);
            vModal += "   </div>";
            vModal += "  </div>";
            vModal += "  </div>";
            vModal += " </div>";
            vModal += "</div>";

            $("body").append($(vModal));

            var vFormAvd = createFormAvd(pColumns, searchText, that),
                timeoutId = 0;
            ;

            $('#avdSearchModalContent' + "_" + that.options.idTable).append(vFormAvd.join(''));

            $('#' + that.options.idForm).off('keyup blur', 'input').on('keyup blur', 'input', function (event) {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(function () {
                    that.onColumntaxonFilter(event);
                }, that.options.searchTimeOut);
            });

            $('#test_button').off('click').on('click', function (event) {

                //test_searchmode = true;

                //console.log(test_request);
                //console.log($(event.currentTarget)[0].id);

                that.onColumntaxonFilter(event);

                //test_searchmode = false;

            });

            $("#btnCloseAvd" + "_" + that.options.idTable).click(function () {
                $("#avdSearchModal" + "_" + that.options.idTable).modal('hide');
            });

            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        } else {
            $("#avdSearchModal" + "_" + that.options.idTable).modal();
        }
    };

    var createFormAvd = function (pColumns, searchText, that) {

        var htmlForm = [];

        htmlForm.push('<button class="btn btn-default center-block" type="button" id="test_button" aria-label="advanced search" title="cc">Filter w/ tet + homo</button> <br>');

        htmlForm.push(sprintf('<form class="form-horizontal" id="%s" action="%s" >', that.options.idForm, that.options.actionForm));
        for (var i in pColumns) {
            var vObjCol = pColumns[i];
            if (!vObjCol.checkbox && vObjCol.visible && vObjCol.searchable) {
                htmlForm.push('<div class="form-group">');
                htmlForm.push(sprintf('<label class="col-sm-4 control-label">%s</label>', vObjCol.title));
                htmlForm.push('<div class="col-sm-6">');
                htmlForm.push(sprintf('<input type="text" class="form-control input-md" name="%s" placeholder="%s" id="%s">', vObjCol.field, vObjCol.title, vObjCol.field));
                htmlForm.push('</div>');
                htmlForm.push('</div>');
            }
        }

        htmlForm.push('<div class="form-group">');
        htmlForm.push('<div class="col-sm-offset-9 col-sm-3">');
        htmlForm.push(sprintf('<button type="button" id="btnCloseAvd%s" class="btn btn-default" >%s</button>', "_" + that.options.idTable, searchText));
        htmlForm.push('</div>');
        htmlForm.push('</div>');
        htmlForm.push('</form>');

        return htmlForm;
    };

    */

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
            return 'Advanced search';
        },
        formatAdvancedCloseButton: function () {
            return "Close";
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

        this.list_taxon_accepted = this.options.taxon_to_show();
        this.multi_species_search = false;
        this.tax_converter = build_tax_to_species_converter(this.options.urlSpecieTree, this.list_taxon_accepted);

        var that = this,
            html = [];

        html.push(sprintf('<div class="dropdown columns columns-%s btn-group pull-%s" role="group">', this.options.buttonsAlign, this.options.buttonsAlign));
        html.push(sprintf('<button class="btn btn-default%s dropdown-toggle' + '" type="button" name="taxonFilter" aria-label="advanced search" title="%s" data-toggle="dropdown">', that.options.iconSize === undefined ? '' : ' btn-' + that.options.iconSize, that.options.formattaxonFilter()));
        html.push(sprintf('<i class="%s %s"></i>', that.options.iconsPrefix, that.options.icons.taxonFilterIcon));
        html.push('<span class="caret"></span>');
        html.push('</button>');
        html.push('<ul class="dropdown-menu">');


        html.push(' <li><a  class="li_filtertax"  id="all">All</a></li> ');

        for (var tax in this.tax_converter) {
            html.push(' <li><a  class="li_filtertax" id="' + tax +'">' + tax +'</a></li> ');
        }

        html.push(' <li class="divider"></li> ');
        html.push(' <li><a  class="li_filtertax"  id="custom">Custom...</a></li> ');

        html.push(' </ul>');
        html.push('</div>');

        that.$toolbar.prepend(html.join(''));

        that.$toolbar.find('a[class="li_filtertax"]')
            .off('click').on('click', function (event) {

                if (this.id === 'custom') {
                    console.log('Custom filtering selection is not yet implemented');
                    //showAvdSearch(that.columns, that.options.formattaxonFilter(), that.options.formatAdvancedCloseButton(), that);
                }

                else{
                        //console.log(event);
                        that.onColumntaxonFilter(event);
                }

        });

        d3.select("#reset_taxon_filter").on('click', function (){

                that.resetSearch();

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
            $('.alert_remove').show();}
        else {
            $('.alert_remove').hide();}

    };

    BootstrapTable.prototype.onColumntaxonFilter = function (event) {

        this.multi_species_search = $(event.currentTarget)[0].id;

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
