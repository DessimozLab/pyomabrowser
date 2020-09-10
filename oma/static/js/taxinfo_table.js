/* Script file for domains visualisations, using the D3 library.
 *
 * -- Alex Warwick Vesztrocy 2015
 */

(function (exports) {
    "use strict";

    var oKeyDeferredMap = {};

     function read_jsondata_from_storage(sKey) {
        var sValue = window.localStorage.getItem(sKey);
        return sValue ? JSON.parse(sValue) : sValue;
    }

    function write_jsondata_to_storage(sKey, oData) {
        var sValue = JSON.stringify(oData);
        while(true) {
            try {
                window.localStorage.setItem(sKey, sValue);
                break;
            } catch (e) {
                localStorage.removeItem(localStorage.key(0));
                continue;
            }
        }
    }

    function cachedAjaxPromise(sUrl, oAjaxOptions) {
        var oDeferred = oKeyDeferredMap[sUrl];
        var sValue;

        if (!oDeferred) {
            oDeferred = new jQuery.Deferred();
            oKeyDeferredMap[sUrl] = oDeferred;
            sValue = read_jsondata_from_storage(sUrl);

            if (sValue) {
                oDeferred.resolve(sValue);
            }

            if (!oAjaxOptions) {
                oAjaxOptions = {};
            }

            $.extend(oAjaxOptions, {
                error: function (oXHR, sTextStatus, sErrorThrown) {
                    console.log('customer info request failed: ' + sErrorThrown);
                    oDeferred.resolve(null);
                },
                success: function (oData) {
                    // making assumption that data is JSON
                    write_jsondata_to_storage(sUrl, oData);
                    oDeferred.resolve(oData);
                }
            });
            $.ajax(sUrl, oAjaxOptions);
        }
        return oDeferred.promise();
    }

    exports.load_all = function (class_of_entries, attr_name) {
        if(attr_name === undefined){ attr_name = 'id'; }
        $.each($(class_of_entries), function (each, value) {
            // Retreive the entry ID
            var entry_id = $(this).attr(attr_name),
                container = $(this).find('.taxinfo_table')[0];


            exports.load_species(container, entry_id);
        });
    };

    exports.load_species = function(container, entry_id) {
        // Grab the domain annotations
        cachedAjaxPromise("/api/genome/"+entry_id.slice(0,5)+"/")
            .done(function (data){
                if (!data) return;





                 container.innerHTML =  '<a href="/oma/genome/'+data.code+'/info">' + data.species  +'</a>';




            });


    };

})(this.taxinfo={});
/**
 * Created by admin on 06.02.20.
 */
