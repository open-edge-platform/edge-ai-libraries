==============
== Licenses ==
==============

GenICam comes in two versions
~ a runtime version
~ a development version.

The runtime version comes under the following license:

  Copyright (c) EMVA and contributors (see source files)
  All rights reserved

  Redistribution and use in source and binary forms, without  modification,
  are permitted provided that the following conditions are met:

  ~ Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.

  ~ Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

  ~ Neither the name of the GenICam standard group nor the names of its contributors
    may be used to endorse or promote products derived from this software without
    specific prior written permission.


  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
  EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
  OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT
  SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
  POSSIBILITY OF SUCH DAMAGE.

The development version comes under the GenICam license (see below).


GenICam uses the following 3rd party software packages:

Package     License         Internet
==================================================================================
Mathparser  LGPL            http://kirya.narod.ru/mathparser.html
                            http://www.sama.ru/~despair/ccalc/
Log4Cpp     LGPL            http://log4cpp.sourceforge.net
CppUnit     LGPL            http://cppunit.sourceforge.net
CLSerAll    NI              http://sourceforge.net/projects/clallserial
xs3p        DSTC            http://xml.fiforms.org/xs3p/index.html
xxhash      New BSD         https://code.google.com/p/xxhash/
XSLTProc    MIT license     http://xmlsoft.org/XSLT/xsltproc2.html
XSDe        Proprietary     NA
PCRE2       BSD license     http://www.pcre.org/

Note that the XSDe license was purchased by one of the members of the committee but 
allows all members to re-compile the parser as long as only the GenApi XML vocabulary is used.
The XSDe free proprietary license is used for the firmware update module.

All license texts come as part of the GenICam distribution in the licenses
subdiretory. If not, you can download them from the internet.

License     File                    Where to find the license texts
==================================================================================
LGPL        LGPL.txt                http://www.gnu.org/licenses/lgpl.html
GenICam     GenICam_License.pdf     http://www.genicam.org
CLSerAll    CLSerAll_LICENSE.txt    http://sourceforge.net/projects/clallserial
xs3p        xs3p_License.mht        http://xml.fiforms.org/xs3p/index.html
xxhash      xxhash_License.txt      http://opensource.org/licenses/BSD-3-Clause
XSLTProc    MIT_License.txt         http://opensource.org/licenses/mit-license.html
XSDe        XSDe License.pdf        NA  
XSDe        Free                    NA
            Proprietary
            License
PCRE2       pcre2_License.txt       http://www.pcre.org/licence.txt

Last but not least GenICam redistributes the C/C++ runtime DLLs of the
Microsoft Visual C++ compiler in the version 12.0

