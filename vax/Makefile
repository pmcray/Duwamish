#
# A LOST TRAVELLER -- the VAX side.
#
#   make simh      fetch and build the SIMH MicroVAX II simulator
#   make           assemble MiniVMS and CDGEN, build the system disk
#   make run       boot MiniVMS (interactive)
#   make run-1985  boot MiniVMS at the speed of a real MicroVAX II
#   make album     render the album on the VAX, then make WAV files and a
#                  burnable BIN/CUE image in build/
#   make clean
#
PYTHON  ?= python3
SIMH    ?= simh/BIN/microvax2
MACRO    = $(PYTHON) tools/macro32.py
VMSDISK  = $(PYTHON) tools/vmsdisk.py
CDDA     = $(PYTHON) tools/cdda.py
B        = build

KERNEL   = minivms/STARLET.MAR minivms/SYSDEF.MAR minivms/BOOT.MAR \
           minivms/CONSOLE.MAR minivms/SUPPORT.MAR minivms/DUDRIVER.MAR \
           minivms/FILES.MAR minivms/SYSSERV.MAR minivms/DCL.MAR \
           minivms/ENDMARK.MAR
TRACKS   = DEPARTURE VISIBILITIES

all: $(B)/MINIVMS.BIN $(B)/CDGEN.EXE $(B)/HELLO.EXE $(B)/TRAVELLER.DSK

$(B)/MINIVMS.BIN $(B)/MINIVMS.STB: $(KERNEL) tools/macro32.py tools/vaxops.py
	@mkdir -p $(B)
	$(MACRO) --format raw --base 0x80000000 -o $(B)/MINIVMS.BIN \
	    -l $(B)/MINIVMS.LIS --stb-out $(B)/MINIVMS.STB $(KERNEL)

$(B)/CDGEN.EXE: cdgen/CDGEN.MAR minivms/STARLET.MAR $(B)/MINIVMS.STB
	$(MACRO) --stb $(B)/MINIVMS.STB -o $@ -l $(B)/CDGEN.LIS \
	    minivms/STARLET.MAR cdgen/CDGEN.MAR

$(B)/HELLO.EXE: examples/HELLO.MAR minivms/STARLET.MAR $(B)/MINIVMS.STB
	$(MACRO) --stb $(B)/MINIVMS.STB -o $@ -l $(B)/HELLO.LIS \
	    minivms/STARLET.MAR examples/HELLO.MAR

# The system disk: an RD54 with the program, its source and the album's
# manuscripts.  (Rebuilt from scratch whenever any of them changes.)
$(B)/TRAVELLER.DSK: $(B)/CDGEN.EXE $(B)/HELLO.EXE cdgen/CDGEN.MAR album/*.MSS
	rm -f $@
	$(VMSDISK) init $@ --label TRAVELLER --owner FREDERICKS --year 1986
	$(VMSDISK) put $@ $(B)/CDGEN.EXE CDGEN.EXE
	$(VMSDISK) put $@ cdgen/CDGEN.MAR CDGEN.MAR
	$(VMSDISK) put $@ minivms/STARLET.MAR STARLET.MAR
	$(VMSDISK) put $@ $(B)/HELLO.EXE HELLO.EXE
	$(VMSDISK) put $@ examples/HELLO.MAR HELLO.MAR
	for f in album/*.MSS; do $(VMSDISK) put $@ $$f; done

$(SIMH):
	@echo "SIMH not found at $(SIMH): run 'make simh' (or set SIMH=...)"; exit 1

simh:
	scripts/get-simh.sh

run: all $(SIMH)
	$(SIMH) scripts/boot.ini

run-1985: all $(SIMH)
	$(SIMH) scripts/boot1985.ini

album: all $(SIMH)
	$(SIMH) scripts/album.ini
	for t in $(TRACKS); do \
	    $(VMSDISK) get $(B)/TRAVELLER.DSK $$t.CDDA $(B)/$$t.CDDA && \
	    $(CDDA) wav $(B)/$$t.CDDA $(B)/$$t.wav; done
	$(CDDA) cue $(B)/A_LOST_TRAVELLER.bin $(foreach t,$(TRACKS),$(B)/$(t).CDDA) \
	    --title "A Lost Traveller"

clean:
	rm -rf $(B) tools/__pycache__

.PHONY: all simh run run-1985 album clean
