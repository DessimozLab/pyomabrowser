/**
 * Created by adriaal on 03/06/16.
 */
(function(exports) {
    var cases = {
        Bacteria: {cls: 'label-success', display_text: "Bacteria", tag: "B"},
        Archaea: {cls: 'label-primary', display_text: "Archaea", tag: "A"},
        Eukaryota: {cls: 'label-danger', display_text: "Eukaryota", tag: "E"},
        _default: {cls: 'label-default', display_text: "unknown", tag: "?"}
    };

    exports.format_as_kindom_tag = function (kingdom) {
        var cur_case = cases[kingdom] ? cases[kingdom] : cases['_default']
        return '<span class="label ' + cur_case.cls + '"><abbr class="abbrNoUnder" ' +
            'title="' + cur_case.display_text + '">' + cur_case.tag + '</abbr></span>';
    }

    exports.format_sciname = function(value, row) {
        return "<b>" + value.species + "</b> " + value.strain;
    }

    exports.add_proteinrow_attrs = function(rowdata, index) {
        return {id: rowdata.protid, 'class': "protein"};
    }

    exports.add_hogrow_attrs = function(rowdata, index) {
        return {id: rowdata.Fam, repr: rowdata.ReprEntryNr, 'class': "hog"};
    }

    exports.format_hogid = function(value, row) {
        return '<a href="/oma/hogs/' + row.ReprEntryNr 
                                      + '/">HOG:'
                                      + ('0000000' + value).slice(-7) // Format with leading 0s
                                      + '</a>';
    }

    exports.format_domainprevalence = function(value, row) {
        return row.PrevCount + ' / ' + row.FamSize;
    }

    exports.format_empty = function(value, row) {
        return "";
    }

    exports.format_info_link = function (value, row) {
        return '<a href="/cgi-bin/gateway.pl?f=DisplayEntry&p1=' + value + '">' + value + '</a>';
    }
    exports.format_vps_link = function(value, row){
        return '<a href="/oma/vps/' + value + '">' + value + '</a>';
    }

    var xref_re = {
        'UniProtKB/SwissProt': {
            re: /[A-Z0-9]{1,5}_[A-Z][A-Z0-9]{2,4}/,
            url: "http://www.uniprot.org/uniprot/",
            img: "reviewed.gif"
        },
        'UniProtKB/TrEMBL': {
            re: /[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}/,
            url: "http://www.uniprot.org/uniprot/",
            img: "unreviewed.gif"
        },
        'Ensembl': {
            re: /ENS[A-Z]{0,3}[PGT]\d{11}/,
            url: "http://www.ensembl.org/id/",
            img: "ensembl.gif"
        },
        'FlyBase': {
            re: /FB[gnptr]{2}\d{7}/,
            url: "http://flybase.org/reports/"
        },
    };

    exports.format_xref = function(value, row) {
        var buf = "";
        $.each(xref_re, function (src, obj) {
            if (obj.re.test(value)) {
                buf = '<a class="external" href="' + obj.url + value
                    + '" title="' + src + '">';
                if (obj.img) {
                    buf += '<img src="'+ static_root + 'image/' + obj.img + '" alt="' + src + '" />&nbsp;'
                }
                buf += value + '</a>';
                return false;
            }
        })
        return buf;
    }
})(this.tablehooks = {});
