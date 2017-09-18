$(document).ready(function() {
    var numberOfSelectedGenome=0;
    var arrayGenome=[];
    var hashGenome=[];
    var maxGenome = 50; //number max of selected genomes
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
    $('#svgg').css('height', viewerHeight - navHeight -110 ); // svgheight = window size - navheight - (some of margin + padding)
    var svgdivHeight = $('#svgdiv').height(); // height of the svgdiv
    var buttonHeight = $('#buttondiv').height();
    $('#UISelected').css('height', svgdivHeight -25 -buttonHeight); //Selectedgenomediv = svgdivheight - margin between the two UI div
    var row3Width = $('#UISelected').width();
    $('#buttonUnselect').css('width', row3Width*0.45 -5);
    $('#buttonSubmit').css('width', row3Width*0.45 -5);
    $('#buttondiv').css('width', row3Width);



    (function() {
        $('#svgg').scroll(function() {
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

    function build_dicts(root){
        // arrayGenome=[];
        // hashGenome=[];
        visit(root, function(d){
            var genometmp=[];

            genometmp[0] = d.name,
            genometmp[1]=d ;
            genometmp[2] = d.id;
            genometmp[3] = d.taxid;
            arrayGenome.push(d.name);
            if(!(d.children || d._children)){arrayGenome.push(d.id);}
            hashGenome.push(genometmp);
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
                selectForExport: [
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
                enableScale: false
            });
            treecomp.viewTree(tree1.name, "svgg");
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
                            urlExport=urlExport+'&p'+i+'='+arrayIdSelectedGenome[i];
                        }
                        OpenInNewTab(urlExport);
                    };
                } else {
                    export_button = document.getElementById('buttonSubmitMarkerGenes')
                    export_button.onclick = function() {
                        var urlExport = "/oma/export_markers/?";
                        urlExport += "min_species_coverage=0.5";
                        urlExport += "&max_nr_markers=1000";
                        for (var i in arrayIdSelectedGenome){
                            urlExport += "&genomes="+arrayIdSelectedGenome[i];
                        }
                        OpenInNewTab(urlExport);
                    };
                }
            })();


            function updateInfo(exportList, root){

                var h3Title = document.getElementById("textSel");
                h3Title.innerHTML='Selected genomes ('  + numberOfSelectedGenome + ')';
                if (numberOfSelectedGenome<=0){h3Title.innerHTML='Selected genomes';}
                $( "#divList" ).remove();
                var divList = document.createElement('div');
                divList.setAttribute('class', 'list-group');
                divList.setAttribute('id', 'divList');
                $("#UISelected").append($(divList));
                for (var i = 0; i < root.leaves.length; i++){
                    if(exportList.indexOf(root.leaves[i].name) !== -1){
                        addToInfo(root.leaves[i])
                    }
                }

                var UISelectedheight = $('#UISelected').height();
                var textSelheight = $('#textSel').height();
                $('#divList').css('maxHeight', UISelectedheight  - textSelheight -20 );
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
