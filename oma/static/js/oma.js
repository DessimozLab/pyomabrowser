/************************ LICENCE ***************************
 *     This file is part of <pyomabrowser>
 *     Copyright (C) <2018> SIB Swiss Institute of Bioinformatics
 *
 *     This program is free software: you can redistribute it and/or modify
 *     it under the terms of the GNU Affero General Public License as
 *     published by the Free Software Foundation, either version 3 of the
 *     License, or (at your option) any later version.
 *
 *     This program is distributed in the hope that it will be useful,
 *     but WITHOUT ANY WARRANTY; without even the implied warranty of
 *     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *     GNU Affero General Public License for more details.
 *
 *     You should have received a copy of the GNU Affero General Public License
 *    along with this program.  If not, see <http://www.gnu.org/licenses/>
 *
 *****************************************************************/
/**
 * File oma.js created on 13/12/18 13:11 by partimo
 * Modified by:
 */
$( document ).ready(function() {
    $("#toggleSidenav").click( function() {
        $('#sideNavMobile').toggle();
        $('#oma-details-sideNav-mobile').toggleClass('sideNavMobile-opened');
    });

    sideBarActivation();
});

// Returns a function, that, as long as it continues to be invoked, will not
// be triggered. The function will be called after it stops being called for
// N milliseconds. If `immediate` is passed, trigger the function on the
// leading edge, instead of the trailing.
function debounce(func, wait, immediate) {
	var timeout;
	return function() {
		var context = this, args = arguments;
		var later = function() {
			timeout = null;
			if (!immediate) func.apply(context, args);
		};
		var callNow = immediate && !timeout;
		clearTimeout(timeout);
		timeout = setTimeout(later, wait);
		if (callNow) func.apply(context, args);
	};
};


var sideBarActivation = debounce(function() {
	if ( $(window).width() < 769) {
        $('.oma-mobile-accordion').click(function () {
            $(this).next('.oma-card-content').slideToggle('fast').siblings('.oma-card-content:visible').slideUp('fast');
            $(this).toggleClass("active").siblings().removeClass('active');
        });
    } else {
        // remove click event from the card header
        $('.oma-mobile-accordion').off( "click");
        // show every cards content
        $('.oma-card-content').show();
    }
}, 250);

window.addEventListener('resize', sideBarActivation);

