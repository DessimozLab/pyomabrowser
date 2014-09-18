$(document).ready(function() {
    var numberOfSelectedGenome=0;
    var arrayGenome=[];
    var hashGenome=[];
    var maxGenome =54; //number max of selected genomes
    var needUpdate=false;//Toolbox need to be update ?
    var dblclick_timer = false;
    var viewerWidth = $(document).width()*0.9;
    var viewerHeight = $(document).height()*0.8;
    var margin = {top: 70, right: 120, bottom: 20, left: 120},
    width = 5500 - margin.right - margin.left,
    height = viewerHeight - margin.top - margin.bottom;
    var i = 0,
    duration = 500,
    root;
    var arrayIdSelectedGenome=[];
    var insearch=false;
    var contectMenu=false;
    var contextNode=null;
    
    var mouse = {x: 0, y: 0}; 
    document.addEventListener('mousemove', function(e){ 
        mouse.x = e.clientX || e.pageX; 
        mouse.y = e.clientY || e.pageY 
    }, false);




    // create the tree
    var tree = d3.layout.tree()
    .size([height, width]);

    //??
    var diagonal = d3.svg.diagonal()
    .projection(function(d) { return [d.y, d.x]; });

    //create the svg countainer, and put it with the margin/offset
    var svg = d3.select("#svgg").append("svg")
    .attr("width", width + margin.right + margin.left)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    //load the data from the Json file
    d3.json("/All/genomes.json", function(error, flare) {
        root = flare;
        root.x0 = height / 2;
        root.y0 = 0;

        //collapse all the nodes at the beginning
        function collapse(d) {
            if (d.children) {
                d._children = d.children;
                d._children.forEach(collapse);
                d.children = null;
            }
        }
        root.children.forEach(collapse);

        //update the tree
        update(root);
    });

    d3.select(self.frameElement).style("height", "width");

    //FUNCTION FOR UPDATE THE TREE

    function update(source) {

        arrayGenome=[];
        hashGenome=[];
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
        function(d) {if (d.children && d.children.length > 0  ){
            return d.children;
        } else if (d._children && d._children.length >0){
            return d._children;
        } 
    });
        //$(function() {$( "#tags" ).autocomplete({source: arrayGenome});});
        

        //recursiv iteration all over the tree to establish the relation father/son
        visit(source,WhoIsDaddy,getChildren);

        //??
        var levelWidth = [1];
        var childCount = function(level, n) {
            if (n.children && n.children.length > 0) {
                if (levelWidth.length <= level + 1) levelWidth.push(0);

                levelWidth[level + 1] += n.children.length;
                n.children.forEach(function(d) {
                    childCount(level + 1, d);
                });
            }
        };
        childCount(0, root);

        var newHeight = d3.max(levelWidth) * 25;   
        d3.select(self.frameElement).style(newHeight, '5500px'); // 5500px must be automaticaly calculate

        // Compute the new tree layout.
        var nodes = tree.nodes(root).reverse(),
        links = tree.links(nodes);

        // Normalize for fixed-depth.
        nodes.forEach(function(d) { d.y = d.depth * 210; });

        // Update the nodes…
        var node = svg.selectAll("g.node")
        .data(nodes, function(d) { return d.id || (d.id = ++i); })


        // Enter any new nodes at the parent's previous position.
        var nodeEnter = node.enter().append("g")
        .attr("class", "node")
        .attr("transform", function(d) { return "translate(" + source.y0 + "," + source.x0 + ")"; })
        .on("click", function(d) {

            if(d.children || d._children){
                addTooltipTaxon(d,d3.event.pageX,d3.event.pageY);
            }
            else
            {
                addTooltipLeaf(d,d3.event.pageX,d3.event.pageY);
            }
        })
        ;
        



    //NODE ENTER

        //Style circles
        nodeEnter.append("circle")
        .attr("r", 1e-6)
        .style("stroke", function(d) { return d._children ? "#22780F" : "#85C17E"; })
        .style("fill", function(d) { return d.isSelected ? "#99d699" : "#fff"; });

        

        //Style the text
        nodeEnter.append("text")
        .attr("x", function(d) { return d.children || d._children ? -10 : 10; })
        .attr("dy", ".35em")
        .attr("text-anchor", function(d) { return d.children || d._children ? "end" : "start"; })
        .text(function(d) { 
            var fullName=d.name;
            var splitName=fullName.split(' ');
            if (splitName[1]){var newName=splitName[0] + ' '+ splitName[1];}
            else{var newName=splitName[0]}
                return d._children || d.children   ? d.name   :  newName + ' ' + d.id; 
        })
        .style("fill-opacity", 1e-6)
        .style('font-style', function(d) { return d._children  || d.children  ? 'normal'  :  'italic' })
        .style('font-weight', function(d) { return d._children || d.children  ? 'bold'  :  'normal' })
        .on("mouseover", function(d) {
            if(!(d._children || d.children)){
                _createNotification(d);
            } 
            ;
        })  
        .on("mouseout",  function(d) {
            if(!(d._children || d.children)){
                $( ".notification" ).remove();
            };
        });

        nodeEnter.append("text")
        .attr("class", "symbol")
        .attr("text-anchor", "middle")
        .attr("dy", ".35em")
        .style('font-weight', 'bold')
        .text(function(d) {
            if (d.children){return'-';}
            else if (d._children){return'+';};
        });


    //TRANSITION + NODE EXIT

        // Transition nodes to their new position.
        var nodeUpdate = node.transition()
        .duration(duration)
        .attr("transform", function(d) { return "translate(" + d.y + "," + d.x + ")"; });

        nodeUpdate.select("circle")
        .attr("r", 5.5)
        .style("fill", function(d) { return d.isSelected ? "#99d699" : "#fff"; });

        nodeUpdate.select("text")
        .style("fill-opacity", 1);

        nodeUpdate.select(".symbol")
        .style("fill-opacity", 1)
        .text(function(d) {
            if (d.children){return'-';}
            else if (d._children){return'+';};
        });
        
        
        // Transition exiting nodes to the parent's new position.
        var nodeExit = node.exit().transition()
        .duration(duration)
        .attr("transform", function(d) { return "translate(" + source.y-500 + "," + source.x-500 + ")"; });

        nodeExit.select("circle")
        .attr("r", 0);

        nodeExit.select("text")
        .style("fill-opacity", 0);

        nodeExit.select(".symbol")
        .style("fill-opacity", 0);

        


    //LINKS

        // Update the links…
        var link = svg.selectAll("path.link")
        .data(links, function(d) { return d.target.id; });

        // Enter any new links at the parent's previous position.
        link.enter().insert("path", "g")
        .attr("class", "link")
        .attr("d", function(d) {
            var o = {x: source.x0, y: source.y0};
            return diagonal({source: o, target: o});
        });

        // Transition links to their new position.
        link.transition()
        .duration(duration)
        .attr("d", diagonal);

        // Transition exiting nodes to the parent's new position.
        link.exit().transition()
        .duration(duration)
        .attr("d", function(d) {
            var o = {x: source.x, y: source.y};
            return diagonal({source: o, target: o});
        })
        .remove();

        // Stash the old positions for transition.
        nodes.forEach(function(d) {
            d.x0 = d.x;
            d.y0 = d.y;
        });

        
        if (needUpdate){
            updateInfo();
            
        }


        if (!(insearch)&& source.father){
            checkChildren(source.father);
        }


    }


    //--------------------------------------------------------------------------------------------------------------
    //--------------------------------------------------------------------------------------------------------------
    //--------------------------------------------------------------------------------------------------------------
    //--------------------------------------------------------------------------------------------------------------


    function updateInfo(){

        var h3Title = document.getElementById("textSel");
        h3Title.innerHTML='Selected genomes ('  + numberOfSelectedGenome + ')';
        if (numberOfSelectedGenome<=0){h3Title.innerHTML='Selected genomes';}
        $( "#divList" ).remove();
        var divList = document.createElement('div');
        divList.setAttribute('class', 'list-group');
        divList.setAttribute('id', 'divList');
        $("#UISelected").append($(divList));
        visit(root,addToInfo,getChildren);
        needUpdate=false;


        var UISelectedheight = $('#UISelected').height();
        var textSelheight = $('#textSel').height();
        $('#divList').css('maxHeight', UISelectedheight  - textSelheight -20 );
    }


    // Toggle children on click.
    function click(d) {
        if (d.children) {
            d._children = d.children;
            d.children = null;
        } else {
            d.children = d._children;
            d._children = null;
        }
        update(d);
    }

    //     FUNCTION

    // Toggle children on click.
    function clickcollapse(d) {
        
        if (d.children) {
            d._children = d.children;
            d.children = null;
        } else {
            d.children = d._children;
        }
        //if (d.children || d._children)
        //{
            //selectTheNode(d);
        //}
        update(d);
    }

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

    //all the children of the node parent receive the attritube 'father' with value 'parent.name'
    function WhoIsDaddy(parent){
        if (parent.children){
            var fan= parent.children;
            for (var i=0; i<fan.length;i++){
                fan[i].father=parent;
            }
        }
        else if (parent._children){
            var fan= parent._children;
            for (var i=0; i<fan.length;i++){
                fan[i].father=parent;
            }
        }
    }

    function getChildren(d){

        if (d.children && d.children.length > 0  ){
            return d.children;
        } else if (d._children && d._children.length >0){
            return d._children;
        } 
    }



    function selectTheNode(d){
        if (numberOfSelectedGenome>maxGenome)
            {return d;}
        d.isSelected=true;
        if(!(d._children || d.children)){
            numberOfSelectedGenome++;
            arrayIdSelectedGenome.push(d.id);
        }
        return d;
    }

    function _selectAlltheBranch(d)
    {
        if (numberOfSelectedGenome==maxGenome+1){
            alert("You have already selected "+ (maxGenome) +" genomes, you have to unselect genomes from the selection before adding new ones.");
        }
        else {
            visit(d,selectTheNode,getChildren);
            needUpdate=true;
            update(d);
            if ( numberOfSelectedGenome>maxGenome){
                alert("The maximum number of selected genomes is "+ (maxGenome) +", so not all genomes in this clade could be selected.");
            }
        }
    }




    function unselectTheNode(d){

        d.isSelected=false;
        if(!(d._children || d.children)){
            for (var i in arrayIdSelectedGenome){
                if (d.id==arrayIdSelectedGenome[i]){
                    removeByIndex(arrayIdSelectedGenome,i);
                    numberOfSelectedGenome--;
                    return d;
                }
            }
        }
        return d;
    }

    function _unSelectAlltheBranch(d)
    {
        visit(d,unselectTheNode,getChildren);
        if (numberOfSelectedGenome<0){
            numberOfSelectedGenome=0;
        } 
        d.isSelected=false;
        needUpdate=true;
        update(d);
    }

    function OpenInNewTab(url) {
        var win = window.open(url, '_blank');
        win.focus();
    }


    function removeByIndex(arr, index) {
        arr.splice(index, 1);
    }

    function checkChildren(d){
        OnechildrenAtLeastSelected=false;

        for (var i in d.children){
            if (d.children[i].isSelected){
                OnechildrenAtLeastSelected=true;
            }
        }
        if(OnechildrenAtLeastSelected){d.isSelected=true;update(d);}
        else {d.isSelected=false;update(d);}
    }

    function _numberChildren(d){
        var numberChildren=0;
        visit(d,function(d){if (!(d.children || d._children)){numberChildren++;}}, function(d) {if (d.children && d.children.length > 0  ){
            return d.children;
        } else if (d._children && d._children.length >0){
            return d._children;
        } 
    });
        return numberChildren;
    }
    function _numberOfSelectedChildren(d){
        var numberSelectedChildren=0;
        visit(d,function(d){if (!(d.children || d._children)&& d.isSelected){numberSelectedChildren++;}}, function(d) {if (d.children && d.children.length > 0  ){
            return d.children;
        } else if (d._children && d._children.length >0){
            return d._children;
        } 
    });
        return numberSelectedChildren;
    }

    function expandAllTheBranch(d){ 
        if ($('.tooltip')){
            $('.tooltip').remove();
            contectMenu=false;
            contextNode=null;
        }
        var source=d;
        insearch=true;
        var path=[];
        while (d){
            path.push(d);
            d=d.father;
        }
        path.reverse();
        path.pop();
        for (var i in path){
            if (!(path[i].children)) {
                path[i].children = path[i]._children;
            }
            update(path[i]);
        }
        insearch=false;
        window.scrollTo(source.y,0);

    }

    function getFather(d){return d.father;}

    function addTooltipTaxon(d, leX, leY){
        if (contextNode==d){
            $('.tooltip').remove();
            contectMenu=false;
            contextNode=null;
            return;
        }
        if ($('.tooltip')){$('.tooltip').remove();}

        var numberChildren= _numberChildren(d);
        var numberSelectedChildren= _numberOfSelectedChildren(d);
        var expandOrCollapse=d.children ? 'collapse' :'Expand';
        var selectOrUnselect=d.isSelected ? 'Unselect all ('  + numberSelectedChildren + ')' : 'Select all (' + numberChildren + ')';
        var div = d3.select("body")
        .append("div")  
        .attr("class", "tooltip")             
        .style("opacity", 0);
        div.transition()
        .duration(200)  
        .style("opacity", .9);  
        div.html( '<button id="expandButton">'+expandOrCollapse+'</button>'+'<button id="selectButton">'+ selectOrUnselect+'</button>' );


        var toolwidth=$('#expandButton').width();
        div.style("left", leX -toolwidth*1.5 + "px")             
        .style("top", leY  +5 + "px");

        (function() {
            document.getElementById("expandButton").onclick = function() { 
                clickcollapse(d);
                $('.tooltip').remove();
                contectMenu=false;
                contextNode=null;
            };
        })();
        (function() {
            document.getElementById("selectButton").onclick = function() {
                if(d.isSelected){
                    _unSelectAlltheBranch(d);
                }
                else{
                    _selectAlltheBranch(d);
                }
                $('.tooltip').remove();
                contectMenu=false;
                contextNode=null;

            };
        })();
        contextNode=d;
        contectMenu=true;

    }

    function addTooltipLeaf(d, leX, leY){
        if (contextNode==d){
            $('.tooltip').remove();
            contectMenu=false;
            contextNode=null;
            return;
        }
        if ($('.tooltip')){$('.tooltip').remove();}
        
        var selectOrUnselect= d.isSelected ? 'Unselect' : 'Select';
        var div = d3.select("body")
        .append("div")  
        .attr("class", "tooltip")             
        .style("opacity", 0);
        div.transition()
        .duration(200)  
        .style("opacity", .9);  
        div.html( '<button id="selectButton">'+selectOrUnselect+'</button>'+'<button id="infoButton">Details</button>' );    
        
        var toolwidth=$('#selectButton').width();
        div.style("left", leX -toolwidth*1.5 + "px")             
        .style("top", leY  +5 + "px");

        (function() {
            document.getElementById("infoButton").onclick = function() { 
                var url= 'http://omabrowser.org/cgi-bin/gateway.pl?f=DisplayOS&p1=' + d.id;
                window.location = url;
            };
        })();
        (function() {
            document.getElementById("selectButton").onclick = function() {
                if(d.isSelected){
                    _unSelectAlltheBranch(d);
                }
                else{
                    _selectAlltheBranch(d);
                }
                $('.tooltip').remove();
                contectMenu=false;
                contextNode=null;

            };
        })();
        contextNode=d;
        contectMenu=true;

    }

    function _createNotification(d){
        var div = d3.select("body")
        .append("div")  
        .attr("class", "notification")             
        .style("opacity", 0);
        div.transition()
        .duration(200)  
        .style("opacity", .9);  
        div.html('<b>'+d.name+ '</b> <br> <strong> ID :</strong> '+ '<i>'+d.id +'</i>'+'<br>'+' <strong> Release :</strong> '+  d.release +'<br>'+' <strong> Clade :</strong> '+  d.father.name)
        //.style("left", leX+ "px")          
        //.style("top", leY  + "px");

        $('.notification').css('top',  mouse.y ); 
        $('.notification').css('left', mouse.x +100 );



    }

    function addToInfo(d)
    {
        if (d.isSelected && !(d._children || d.children)){

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
            cladeList.innerHTML+=d.father.name;
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
            
            find.onclick=function(){expandAllTheBranch(d);};
            Clade.onclick=function(){expandAllTheBranch(d.father);};
            deleteB.onclick=function(){
                unselectTheNode(d);
                needUpdate=true;
                update(d);

            };
            
            
        }
    }




            var viewerHeight = $(document).height();  //height of the browser window
            var navHeight = $('#navbb').height(); // height of the navbar
            $('#svgg').css('height', viewerHeight - navHeight -50 ); // svgheight = window size - navheight - (some of margin + padding)
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


            (function() {
                document.getElementById("buttonUnselect").onclick = function() { 
                    visit(root,function(d){d.isSelected=false},getChildren);
                    numberOfSelectedGenome=0;
                    arrayIdSelectedGenome=[];

                    needUpdate=true;
                    update(root);
                };
            })();

            (function() {
                document.getElementById("buttonSubmit").onclick = function() { 
                    var urlExport= 'http://omabrowser.org/cgi-bin/gateway.pl?f=AllAllExport';
                    for (var i in arrayIdSelectedGenome){
                        urlExport=urlExport+'&p'+i+'='+arrayIdSelectedGenome[i];
                    }
                    OpenInNewTab(urlExport);    
                };
            })();

    (function() {
        document.getElementById("searchGenome").onclick = function() { 
            var selectname =document.getElementById('tags').value;
            if (hashGenome){
                for (var i=0; i<hashGenome.length;i++){
                    if (hashGenome[i][0]==selectname){
                        var searchGenomeGo=hashGenome[i][1];
                        expandAllTheBranch(searchGenomeGo);
                        return;
                    }
                    else if (hashGenome[i][2]==selectname){
                        var searchGenomeGo=hashGenome[i][1];
                        expandAllTheBranch(searchGenomeGo);
                        return;
                    }
                    else if (hashGenome[i][3]==selectname){
                        var searchGenomeGo=hashGenome[i][1];
                        expandAllTheBranch(searchGenomeGo);
                        return;
                    }
                }
            } 
        };
    })();
});
