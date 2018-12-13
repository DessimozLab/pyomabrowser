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
});

if ( $(window).width() < 769) {
    $('.oma-mobile-accordion').click(function () {
        $(this).next('.oma-card-content').slideToggle('fast').siblings('.oma-card-content:visible').slideUp('fast');
        $(this).toggleClass("active").siblings().removeClass("active");
    });
}
