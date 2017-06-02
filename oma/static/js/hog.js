"use strict";

var hog_theme;

hog_theme = function (settings_theme) {

    // settings_theme is the settings variable for hog_theme, it can be customize by using the settings_theme parameter
    var settings_theme = settings_theme || {};

    // label_height defines the text size of the tree labels and indirectly the square sizes.
    settings_theme.label_height = settings_theme.hasOwnProperty('label_height') ? settings_theme.label_height : 20;

    var genedatavis_default = [{
        name: 'Query Gene',
        scale: 'on_off'
    },
        {
            name: "Gene Length",
            scale: "linear",
            field: "sequence_length",
            func: "color1d"
        },
        {
            name: "EC Content",
            scale: "linear",
            field: "ec_content",
            func: "color1d"
        }
    ];

    // genedatavis defines the type of data used to color the gene square and the related color scheme.
    settings_theme.genedatavis = settings_theme.hasOwnProperty('genedatavis') ? settings_theme.genedatavis : genedatavis_default;

    // Hogvis is the main object to be created, it take a div and others parameters to set up an hogvis instance
    function Hogvis(hogvis_container, query_gene, per_species3, tree_obj, gene_data, options, genedata_picker_div) {

        ////////////////////
        ///// OPTIONS //////
        ////////////////////

        // options is the options variable for Hogvis, it can be customize by using the options parameter
        var options = options || {};

        // display or not internal node label
        options.show_internal_labels = options.hasOwnProperty('show_internal_labels') ? options.show_internal_labels : "true";

        // redirection url prefix for tooltip on genes
        options.oma_info_url_template = options.hasOwnProperty('oma_info_url_template') ? options.oma_info_url_template : "/cgi-bin/gateway.pl?f=DisplayEntry&amp;p1=";

        // div id of the open at "xxx" text div
        options.current_level_div = options.hasOwnProperty('current_level_div') ? options.current_level_div : "current_level_text";

        ////////////////////
        //// VARIABLES /////
        ////////////////////

        // name of the current taxa displayed
        var current_opened_taxa_name = '';

        // todo
        var is_node_frozen = false;

        // todo
        var fam_genedata;

        // todo
        var gene_color_function;

        // div that display the name of the currently opened level
        var div_current_level = document.getElementById(options.current_level_div);

        // total with of the hogvis container
        var tot_width = parseInt(d3.select(hogvis_container).style("width")) - 30; // todo -30 should be define by margin variables

        // todo
        var maxs = get_maxs(per_species3);

        //todo
        var gene_color_data;

        // todo + ADRIAN: What is the use of this
        var gene_color_scale = d3.scale.category10();

        // todo
        var col_scale;

        //todo
        var colorbar;

        /////////////
        // TREE /////
        /////////////

        // Nodes shapes / colors
        var collapsed_node = tnt.tree.node_display.triangle()
            .fill("grey")
            .size(4);

        var leaf_node = tnt.tree.node_display.circle()
            .fill("#2c3e50")
            .size(4);

        var int_node = tnt.tree.node_display.circle()
            .fill("#34495e")
            .size(4);

        var highlight_node = tnt.tree.node_display.circle()
            .fill("#e74c3c")
            .size(6);

        var highlight_condition = function () {
            return false;
        };

        var node_display = tnt.tree.node_display()
            .display(function (node) {
                if (highlight_condition(node)) {
                    highlight_node.display().call(this, node);
                } else if (node.is_collapsed()) {
                    collapsed_node.display().call(this, node);
                } else if (node.is_leaf()) {
                    leaf_node.display().call(this, node);
                } else if (!node.is_leaf()) {
                    int_node.display().call(this, node);
                }
            });

        // Node tooltip
        var treeNode_tooltip = tnt.tooltip()
            .fill(function (node) {
                // The DOM element is passed as "this"
                var container = d3.select(this);

                var table = container
                    .append("table")
                    .attr("class", "tnt_zmenu")
                    .attr("border", "solid")

                table
                    .append("tr")
                    .attr("class", "tnt_zmenu_header")
                    .append("th")
                    .text(node.node_name());

                // There is 3 freezing possibilites: "Freeze tree at this node", "Unfreeze the tree", "Re-freeze tree at this node"

                table
                    .append("tr")
                    .attr("class", "tnt_zmenu_row")
                    .append("td")
                    .style("text-align", "center")
                    .html(function () {
                        return is_node_frozen ? "<a>Unfreeze the tree</a>" : "<a>Freeze tree at this node</a>"
                    })
                    .on("click", function () {
                        if (is_node_frozen) {
                            is_node_frozen = false;
                        }
                        else {
                            is_node_frozen = node.id;
                        }
                        treeNode_tooltip.close();
                    });

                if (is_node_frozen && is_node_frozen != node.id) {

                    table
                        .append("tr")
                        .attr("class", "tnt_zmenu_row")
                        .append("td")
                        .style("text-align", "center")
                        .html("<a>Re-freeze tree at this node</a>")
                        .on("click", function () {
                            is_node_frozen = false;
                            mouse_over_node(node);
                            is_node_frozen = node.id;
                            treeNode_tooltip.close();
                        });

                }


                if (!node.is_leaf() || node.is_collapsed()) {
                    table
                        .append("tr")
                        .attr("class", "tnt_zmenu_row")
                        .append("td")
                        .style("text-align", "center")
                        .html(function () {
                            return node.is_collapsed() ? "<a> Uncollapse subtree </a>" : "<a> Collapse subtree </a>"
                        })
                        .on("click", function () {
                            node.toggle();
                            vis.update();
                            treeNode_tooltip.close();
                        });
                }


            });

        // mouse over a node
        var node_hover_tooltip;
        var mouse_over_node = function (node) {
            // Update annotation board
            if (is_node_frozen) {
                return;
            }

            current_opened_taxa_name = node.node_name();
            div_current_level.innerHTML = current_opened_taxa_name;
            annot.update();

            // when update the board make sure that the scroll is reset to left
            var annot_scroller = $('#tnt_annot_container_hog_vis');
            annot_scroller.scrollLeft(0);

            highlight_condition = function (n) {
                return node.id() === n.id();
            };
            tree.update_nodes();

            // Show a mouse over tooltip for internal nodes
            if (!options.show_internal_labels && node.data().children && node.data().children.length) {
                var obj = {};
                obj.header = "";
                obj.body = node.node_name();
                node_hover_tooltip = tooltip.plain()
                    .width(140)
                    .show_closer(false)
                    .position("left")
                    .call(this, obj);
            }
        };

        // node mouseout
        var mouse_out_node = function (node) {
            if (!options.show_internal_labels) {
                node_hover_tooltip.close();
            }
        };

        var init_tree = function(){
            var t = tnt.tree()
                .data(tree_obj)
                .layout(tnt.tree.layout.vertical()
                    .width(Math.max(240, ~~(tot_width * 0.4)))
                    .scale(false)
                )
                .label(tnt.tree.label.text()
                    .fontsize(12)
                    .height(settings_theme.label_height)
                    .text(function (node) {
                        var limit = 30;
                        var data = node.data();
                        if (node.is_collapsed()) {
                            return "[" + node.n_hidden() + " hidden taxa]";
                        }
                        if ((!options.show_internal_labels || !highlight_condition(node)) &&
                            data.children && data.children.length > 0) {
                            return "";
                        }
                        if (data.name.length > limit) {
                            var truncName = data.name.substr(0, limit - 3) + "...";
                            return truncName.replace(/_/g, ' ');
                        }
                        return data.name.replace(/_/g, ' ');
                    })
                    .color(function (node) {
                        if (node.is_collapsed()) {
                            return 'grey';
                        }
                        return 'black';
                    })
                    .fontweight(function (node) {
                        if (highlight_condition(node)) {
                            return "bold";
                        }
                        return "normal";
                    })
                )
                .on("click", function (d) {
                    treeNode_tooltip.call(this, d);
                })
                .on("mouseover", mouse_over_node)
                .on("mouseout", mouse_out_node)
                .node_display(node_display)
                .branch_color("black");
            return t;
        };

        var tree = init_tree();

        // Once the tree is build update the current level opened with the root by default
        current_opened_taxa_name = tree.root().node_name();

        /////////////////////////
        ///// GENES PANEL ///////
        /////////////////////////

        var gene_tooltip = function (gene) {
            var obj = {};
            obj.header = gene_data[gene.id].omaid;
            obj.rows = [];
            obj.rows.push({label: "Name", value: gene_data[gene.id].id});
            obj.rows.push({
                label: "Information",
                obj: gene,
                value: "<a href='" + options.oma_info_url_template + gene.id + "'>" + gene_data[gene.id].omaid + "</a>"
            });

            tnt.tooltip.table()
                .container(document.getElementsByClassName("tnt_groupDiv")[0])
                .call(this, obj);
        };

        // TnT doesn't have the features we need, so create our own
        // This one if for the lines defining hogs
        var hog_feature = tnt.board.track.feature();
        hog_feature
            .index(function (d) {
                return d.id;
            })
            .create(function (new_hog, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                new_hog
                    .append("line")
                    .attr("class", "hog_boundary")
                    .attr("x1", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * (d.max_in_hog - 1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width) / 2 + ~~(padding / 2) - 1;
                    })
                    .attr("x2", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * (d.max_in_hog - 1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width) / 2 + ~~(padding / 2) - 1;
                    })
                    .attr("y1", 0)
                    .attr("y2", track.height())
                    .attr("stroke-width", 2)
                    .attr("stroke", "#34495e");
            })
            .distribute(function (hogs, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                hogs.select("line")
                    .transition()
                    .duration(200)
                    .attr("x1", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * (d.max_in_hog - 1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width) / 2 + ~~(padding / 2) - 1;
                    })
                    .attr("x2", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * (d.max_in_hog - 1);
                        var xnext = width * d.max_in_hog;
                        return x + (xnext - x + width) / 2 + ~~(padding / 2) - 1;
                    });
            });

        var hog_gene_feature = tnt.board.track.feature();
        hog_gene_feature
            .index(function (d) {
                return d.id;
            })
            .create(function (new_elems, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                new_elems
                    .append("rect")
                    .attr("class", function (d) {
                        return "hog_gene" + (query_gene && d.id === query_gene.id ? " ref_gene" : "" )
                    })
                    .attr("x", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * d.pos;
                        return x + padding;
                    })
                    .attr("y", padding)
                    .attr("width", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        return width - 2 * padding;
                    })
                    .attr("height", height)
                    .attr("fill", gene_color_function);
            })
            .distribute(function (elems, x_scale) {
                var track = this;
                var padding = ~~(track.height() - (track.height() * 0.8)) / 2; // TODO: can this be factored out??
                // otherwise it is repeated with every create event

                var height = track.height() - ~~(padding * 2);
                var dom1 = x_scale.domain()[1];

                elems.select("rect")
                    .transition()
                    .duration(200)
                    .attr("x", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        var x = width * d.pos;
                        return x + padding;
                    })
                    .attr("width", function (d) {
                        var width = d3.min([x_scale(dom1 / d.max), height + 2 * padding]);
                        return width - 2 * padding;
                    })
                    .attr("fill", gene_color_function);

            })
            .on("mouseover", gene_tooltip);

        var annot = tnt.board()
            .from(0)
            .zoom_in(1)
            .allow_drag(false)
            .to(5)
            .width(~~(tot_width * 0.6));

        var track = function (leaf) {
            var sp = leaf.node_name();
            return tnt.board.track()
                .color("#FFF")
                .data(tnt.board.track.data.sync()
                    .retriever(function () {
                        // return _.flatten(per_species2[sp].Vertebrates);
                        // return per_species2[sp].Vertebrates;
                        if (per_species3[sp] === undefined) {
                            return {
                                genes: [],
                                hogs: []
                            };
                        }
                        var genes2Xcoords = genes_2_xcoords(per_species3[sp][current_opened_taxa_name], maxs[current_opened_taxa_name]);
                        return genes2Xcoords;
                    })
                )
                .display(tnt.board.track.feature.composite()
                    .add("genes", hog_gene_feature)
                    .add("hogs", hog_feature)
                );
        };

        var genes_2_xcoords = function (arr, maxs) {
            if (arr === undefined) {
                return {
                    genes: [],
                    hogs: []
                };
            }
            var genes = [];
            var hogs_boundaries = [];
            var total_pos = 0;
            arr.forEach(function (hog_genes, hog) {
                var hog_gene_names = [];
                hog_genes.sort();
                hog_genes.forEach(function (gene, gene_pos) {
                    genes.push({
                        id: gene,
                        hog: hog,
                        pos: total_pos + gene_pos,
                        max: d3.sum(maxs),
                        max_in_hog: maxs[hog],
                        pos_in_hog: gene_pos
                    });
                    hog_gene_names.push(gene);
                });
                total_pos += maxs[hog];
                hogs_boundaries.push({
                    max: d3.sum(maxs),
                    max_in_hog: total_pos,
                    hog: hog,
                    id: hog_gene_names.length ? hog_gene_names.join('_') : ("hog_" + hog)
                });
            });

            return {
                genes: genes,
                hogs: hogs_boundaries.slice(0, -1)
            };
        };

        var change_genedata_vis = function (d) {
            col_scale = undefined;
            gene_color_function = function (gene) {
                return (query_gene && gene.id === query_gene.id ? "#27ae60" : "#95a5a6");
            };
            if (fam_genedata === undefined) {
                $.getJSON("/oma/hogdata/" + query_gene.id + "/json", function (data) {
                    fam_genedata = {};
                    data.forEach(function (gene) {
                        fam_genedata[gene.id] = gene;
                    });
                    change_genedata_vis(d);
                });
                return;
            }

            var field = d.field;
            if (d.func === "color1d") {
                col_scale = d3.scale.linear()
                    .domain(d3.extent(d3.values(fam_genedata)
                        .map(function (gene) {
                            return gene[field];
                        })))
                    .range([d3.rgb("#e74c3c"), d3.rgb('#3498db')]);
                gene_color_function = function (gene) {
                    return col_scale(fam_genedata[gene.id][field]);
                };
            }
            ;
            annot.update();
            vis.update();

        };

        change_genedata_vis(settings_theme.genedatavis[0]);

        var genedata_picker = d3.select(genedata_picker_div).selectAll(".genedata-li")
            .data(settings_theme.genedatavis);

        var bar = d3.select("#colorbar");

        var barText = d3.select('[id="colorbarText"]')[0][0]; // )0_o(

        genedata_picker.enter()
            .append("li")
            .attr("value", function (d) {
                return d.name
            })
            .html(function (d) {
                return "<a>" + d.name + "</a>"
            })
            .attr("class", "genedata-li")
            .on("click", function (d) {
                change_genedata_vis(d);
                if (col_scale) {
                    colorbar = Colorbar()
                        .origin([Math.max(200, ~~(tot_width * 0.4)), 0])
                        .scale(col_scale)
                        .orient('horizontal')
                        .thickness(18)
                        .barlength(~~(tot_width * 0.6));
                    bar.call(colorbar);
                    barText.innerHTML = d.name;
                } else {
                    bar.selectAll("svg").remove();
                    barText.innerHTML = null;
                }
            });

        ///////////////////
        ///// HOGVIS //////
        ///////////////////

        var vis = tnt()
            .tree(tree)
            .board(annot)
            .track(track);
        vis(hogvis_container);

        // open at root level when created
        mouse_over_node(tree.root());

        // make board panel sticky to tree panel and right
        set_board_width_on_window_resize();

        // make hogvis header block (scale, hogid, etc..) fixed to top when scroll
        set_fixed_header_on_window_scroll();

        // make the vis panel resizable
        set_resize_on_drag(tree);

        // function to set up drag to resize tree and board panel
        // rearranged code from http://stackoverflow.com/questions/26233180/resize-div-on-border-drag-and-drop
        function set_resize_on_drag(tree_to_resize) {

            // Add a drag div between tree and board panel
            var dragDiv = document.createElement("div");
            var tree_panel = document.getElementById("tnt_tree_container_hog_vis");
            dragDiv.id = 'drag';
            dragDiv.style.height = $("#tnt_tree_container_hog_vis").height() + "px";
            tree_panel.parentNode.insertBefore(dragDiv, tree_panel.nextSibling);

            var isResizing = false,
                lastDownX = 0;

            var container = $('#hog_vis'),
                left = $('#tnt_tree_container_hog_vis'),
                right = $('#tnt_annot_container_hog_vis'),
                handle = $('#drag');

            handle.on('mousedown', function (e) {
                isResizing = true;
                lastDownX = e.clientX;
            });

            $(document).on('mousemove', function (e) {
                // we don't want to do anything if we aren't resizing.
                if (!isResizing)
                    return;

                // compute the new width of tree panel
                var nw = e.clientX - container.offset().left;
                //make sure that we left at least 50 px to the board panel and that at least 50 px large
                var nwld = Math.min(container.width() - 50, nw);
                nwld = Math.max(50, nwld);

                // resize tree panel to new width and update board panel
                left.css('width', nwld);
                set_scroller_width();

                // update the tree according to the new tree panel size with min 100px width
                tree_to_resize.layout().width(Math.max(200, nwld - 20));
                tree_to_resize.update();
            }).on('mouseup', function (e) {
                // stop resizing
                isResizing = false;

            });
        }

    };

    var truncate = function (text, width) {
        text.each(function () {
            var text = d3.select(this),
                full_text = text.text(),
                low = 0, up = full_text.length, m;
            if (text.node().getComputedTextLength() > width) {
                while (low < up) {
                    m = ~~((low + up) / 2);
                    text.text(full_text.slice(0, m) + "...");
                    if (text.node().getComputedTextLength() < width) {
                        low = m;
                    } else {
                        up = m;
                    }
                }
            }
        })
    }

    // get maximum number of genes per hog accross species
    var get_maxs = function (ps2) {
        var maxs = {};
        var i, sp, internal;
        for (sp in ps2) {
            if (ps2.hasOwnProperty(sp)) {
                var sp_data = ps2[sp];
                for (internal in sp_data) {
                    if (maxs[internal] === undefined) {
                        maxs[internal] = [];
                    }
                    if (sp_data.hasOwnProperty(internal)) {
                        var internal_data = sp_data[internal];
                        for (i = 0; i < internal_data.length; i++) {
                            if ((maxs[internal][i] === undefined) ||
                                (maxs[internal][i] < internal_data[i].length)) {
                                maxs[internal][i] = internal_data[i].length;
                            }
                        }
                    }
                }
            }
        }
        return maxs;
    };

    // resize the board container to fill space between tree panel and right
    function set_scroller_width() {

        var viewerC = document.getElementById("hog_vis");
        var viewerS = document.getElementById("tnt_annot_container_hog_vis");
        var viewerT = document.getElementById("tnt_tree_container_hog_vis");

        var scroller_width = viewerC.offsetWidth - viewerT.offsetWidth - 40;
        viewerS.style.width = scroller_width + "px";

        $('#hogvisheader').width($('#hogs').width() - 20); // Because padding of #hogs is 10px


    }

    // function to set up automatic board resizing on window resize
    function set_board_width_on_window_resize() {

        set_scroller_width();

        window.onresize = function () {
            set_scroller_width();
        }
    }

    // function to fixed the hogvis header block to top when scroll
    function set_fixed_header_on_window_scroll() {
        var stickyHeaderTop = $('#hogvisheader').offset().top;
        $(window).scroll(function () {
            if ($(window).scrollTop() > stickyHeaderTop) {
                $('#hogvisheader').css({
                    position: 'fixed',
                    top: '0px'
                });
                $('#hog_vis').css('margin-top', $('#hogvisheader').outerHeight(true) + parseInt($('#gap_conpenser').css('marginBottom')));
            } else {
                $('#hogvisheader').css({
                    position: 'static',
                    top: '0px'
                });
                $('#hog_vis').css('margin-top', '0px');
            }
        });
    };

    return Hogvis;
};
