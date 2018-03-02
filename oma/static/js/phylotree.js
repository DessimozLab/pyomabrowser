$(document).ready(function() {
    var numberOfSelectedGenome=0;
    var maxGenome = window.MAX_NR_GENOMES || 50; //number max of selected genomes
    var hashGenome={};
    var needUpdate=false;//Toolbox need to be update ?
    var arrayIdSelectedGenome=[];
    // var insearch=false;
    var contectMenu=false;
    var contextNode=null;
    // var tooManyGenomesInBranch=false;

    var mouse = {x: 0, y: 0};
    document.addEventListener('mousemove', function(e){
        mouse.x = e.clientX || e.pageX;
        mouse.y = e.clientY || e.pageY
    }, false);

    var viewerHeight = $(document).height();  //height of the browser window
    var navHeight = $('#navbb').height(); // height of the navbar
    $('#phylo_io').css('height', viewerHeight - navHeight -110 ); // svgheight = window size - navheight - (some of margin + padding)
    var svgdivHeight = $('#svgdiv').height(); // height of the svgdiv
    var buttonHeight = $('#buttondiv').height();
    var exportAdditionalInputs = $('#exportAdditionalInputs').height();
    $('#UISelected').css('height', svgdivHeight - 15 - 25 - buttonHeight - exportAdditionalInputs); //Selectedgenomediv = svgdivheight - margin btw additional input div - margin between the two UI div - height of additional input div
    var row3Width = $('#UISelected').width();
    $('#buttonUnselect').css('width', row3Width*0.45 -5);
    $('#buttonSubmit').css('width', row3Width*0.45 -5);
    $('#buttondiv').css('width', row3Width);



    (function() {
        $('#phylo_io').scroll(function() {
            if ($('.tooltip')){
                $('.tooltip').remove();
                contectMenu=false;
                contextNode=null;
            }
        });
    })();

    //Recursive tree visit with function for the actual node and for select children
    function visit(parent, visitFn, childrenFn) {
        if (!parent) return;
        visitFn(parent);
        var children = childrenFn(parent);
        if (children) {
            var count = children.length;
            for (var i = 0; i < count; i++) {
                visit(children[i], visitFn, childrenFn);
            }
        }
    }

    function OpenInNewTab(url) {
        var win = window.open(url, '_blank');
        win.focus();
    }

    function build_dicts(root){
        visit(root, function(d){
            if(!(d.children || d._children)){
                hashGenome[d.name] = d.id
            }
        },
        function(d) {
            if (d.children && d.children.length > 0  ){
                return d.children;
            } else if (d._children && d._children.length >0){
                return d._children;
            }
        });
    };
    //
    //
    // //load the data from the Json file
    $.ajax({
        url: "/All/genomes.json",
        success: function (newick) {
            var additionalNodeFunctions = {
                "selectForExport": [
                    function(exportList){
                        arrayIdSelectedGenome = exportList;
                        updateInfo(arrayIdSelectedGenome, tree1.root)
                    }
                ]
            };

            var treecomp = TreeCompare().init({
                maxNumGenome: maxGenome,
                nodeFunc: additionalNodeFunctions
            });
            var tree1 = treecomp.addTree(newick, undefined);
            treecomp.changeCanvasSettings({
                autoCollapse: 0, //tree1.data.autoCollapseDepth,
                enableScale: false,
                enableSharing: false
            });
            treecomp.viewTree(tree1.name, "phylo_io");
            needUpdate = true;

            build_dicts(tree1.root);

            (function() {
                document.getElementById("buttonUnselect").onclick = function() {
                    numberOfSelectedGenome=0;
                    arrayIdSelectedGenome.splice(0, arrayIdSelectedGenome.length);
                    treecomp.unselect(tree1.root);
                    updateInfo(arrayIdSelectedGenome, tree1.root);
                };
            })();

            (function() {
                var export_button = document.getElementById("buttonSubmit");

                if (export_button) {
                    export_button.onclick = function() {
                        var urlExport= '/cgi-bin/gateway.pl?f=AllAllExport';
                        for (var i in arrayIdSelectedGenome){
                            urlExport=urlExport+'&p'+i+'='+hashGenome[arrayIdSelectedGenome[i]];
                        }
                        OpenInNewTab(urlExport);
                    };
                } else {
                    export_button = document.getElementById('buttonSubmitMarkerGenes');
                    export_button.onclick = function() {
                        var urlExport = "/oma/export_markers/?";
                        var min_species_coverage = document.getElementById('min_species_coverage_input').value;
                        var max_nr_markers = document.getElementById('max_nr_markers_input').value;
                        var sp_frac = 0.5;
                        if (min_species_coverage !== ''){
                            var sp_frac = parseFloat(min_species_coverage)
                            if (sp_frac <= 0 || sp_frac > 1){
                                alert('Minimum fraction of covered species must in range (0, 1]');
                                return;
                            }
                        }
                        urlExport += "min_species_coverage=" + sp_frac;
                        if (max_nr_markers !== ''){
                            var nr_markers = parseInt(max_nr_markers, 10);
                            if (isNaN(nr_markers)){
                                alert("Maximum number of markers must be a value");
                                return;
                            }
                            urlExport += "&max_nr_markers="+nr_markers;

                        }
                        for (var i in arrayIdSelectedGenome){
                            urlExport += "&genomes="+hashGenome[arrayIdSelectedGenome[i]];
                        }
                        OpenInNewTab(urlExport);
                    };
                }
            })();


            function updateInfo(exportList, root){

                numberOfSelectedGenome = exportList.length;
                var h3Title = document.getElementById("textSel");
                h3Title.innerHTML='Selected genomes ('  + numberOfSelectedGenome + ')';
                if (numberOfSelectedGenome<=0){h3Title.innerHTML='Selected genomes';}
                $( "#divList" ).remove();
                var divList = document.createElement('div');
                divList.setAttribute('class', 'list-group');
                divList.setAttribute('id', 'divList');
                //$("#UISelected").append($(divList));
                $("#UISelectedContent").append($(divList));
                for (var i = 0; i < root.leaves.length; i++){
                    if(exportList.indexOf(root.leaves[i].name) !== -1){
                        addToInfo(root.leaves[i])
                    }
                }

                //var UISelectedheight = $('#UISelected').height();
                //var textSelheight = $('#textSel').height();
                //$('#divList').css('maxHeight', UISelectedheight  - textSelheight -20 );
                var UISelectedheight = $('#UISelected').height();
                var textSelheight = $('#UISelectedHeading').height();
                var UISelectedContentPadding = parseFloat($('.panel-body').css('padding-top')) + parseFloat($('.panel-body').css('padding-bottom'));
                $('#divList').css('maxHeight', UISelectedheight - textSelheight - 22 - UISelectedContentPadding);
            }

            function addToInfo(d) {
                if (!(d._children || d.children)){

                    var ptr = document.createElement('div');
                    ptr.setAttribute('class','list-group-item');

                    var deleteB = document.createElement('button');
                    deleteB.innerHTML= '<span aria-hidden="true">&times;</span>';
                    deleteB.setAttribute('class', 'close');

                    var pName = document.createElement('strong');
                    pName.innerHTML='<b>'+d.name+ '</b>'  ;
                    pName.setAttribute('class', 'pName');

                    var find = document.createElement('button');
                    find.innerHTML=  ' <em(locate on tree)</em>' ;
                    find.style.color='#666666';
                    find.setAttribute('class', 'nameGenomes');

                    var Clade = document.createElement('em');
                    Clade.innerHTML='Clade : </strong>';

                    var ID = document.createElement('em');
                    ID.innerHTML='ID : ';

                    var IDA = document.createElement('a');
                    IDA.innerHTML= d.id +'  '+'<img alt="ext logo" src="/static/image/ext.png" ></a>' ;
                    IDA.href="/cgi-bin/gateway.pl?f=DisplayOS&p1="+d.id;

                    var TAXID = document.createElement('em');
                    TAXID.innerHTML='Taxon ID : ';

                    var TAXIDA = document.createElement('a');
                    TAXIDA.innerHTML= d.taxid +'  '+'<img alt="ext logo" src="/static/image/ext.png" ></a>' ;
                    TAXIDA.href="http://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?mode=Info&id="+d.taxid;

                    var headerList = document.createElement('div');
                    headerList.appendChild(pName);
                    headerList.appendChild(find);
                    headerList.appendChild(deleteB);
                    headerList.setAttribute('class', 'headerList');

                    var cladeList = document.createElement('div');
                    cladeList.appendChild(Clade);
                    cladeList.innerHTML+=d.parent.name;
                    cladeList.innerHTML+='<br>'
                    cladeList.setAttribute('class', 'cladeList');

                    var IDList = document.createElement('div');
                    IDList.appendChild(ID);
                    IDList.appendChild(IDA);
                    IDList.innerHTML+=' ';
                    IDList.appendChild(TAXID);
                    IDList.appendChild(TAXIDA);
                    IDList.innerHTML+='<br>';
                    IDList.setAttribute('class', 'IDList');

                    var relList = document.createElement('div');
                    relList.innerHTML+='<em>Release : </em>'+ d.release;
                    relList.setAttribute('class', 'relList');

                    ptr.appendChild(headerList);
                    ptr.appendChild(cladeList);
                    ptr.appendChild(IDList);
                    ptr.appendChild(relList);

                    $(".list-group").append($(ptr));

                    //add the function for delete a genome or get his OMA page>

                    // find.onclick=function(){expandAllTheBranch(d);};
                    // Clade.onclick=function(){expandAllTheBranch(d.father);};
                    deleteB.onclick=function(){
                        for (var i = 0; i < arrayIdSelectedGenome.length; i++){
                            if (d.name === arrayIdSelectedGenome[i]){
                                arrayIdSelectedGenome.splice(i,1);
                            }
                        }
                        treecomp.unselect(d);
                        updateInfo(arrayIdSelectedGenome, tree1.root);

                    };


                }
            }

        },
        dataType: "text"
    });

});
