/**
 * @author  Thomas Holterbach
 * @email   thomasholterbach@gmail.com
 * @date    13/01/17
 * @info    To use with Floodlight v1.1 only
 */

package net.floodlightcontroller.arphandler;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;

import java.util.Collection;
import java.util.Map;
import java.util.List;
import java.util.Set;

import org.projectfloodlight.openflow.protocol.OFMessage;
import org.projectfloodlight.openflow.protocol.OFType;
import org.projectfloodlight.openflow.protocol.OFPacketIn;
import org.projectfloodlight.openflow.types.MacAddress;
import org.projectfloodlight.openflow.protocol.OFPacketOut;
import org.projectfloodlight.openflow.protocol.action.OFAction;
import org.projectfloodlight.openflow.protocol.action.OFActionOutput;
import org.projectfloodlight.openflow.types.OFPort;
import org.projectfloodlight.openflow.types.OFBufferId;
import org.projectfloodlight.openflow.types.EthType;

import net.floodlightcontroller.packet.ARP;
import net.floodlightcontroller.packet.IPv4;
import net.floodlightcontroller.packet.IPacket;
import net.floodlightcontroller.packet.Data;


import net.floodlightcontroller.core.FloodlightContext;
import net.floodlightcontroller.core.IOFMessageListener;
import net.floodlightcontroller.core.IOFSwitch;
import net.floodlightcontroller.core.module.FloodlightModuleContext;
import net.floodlightcontroller.core.module.FloodlightModuleException;
import net.floodlightcontroller.core.module.IFloodlightModule;
import net.floodlightcontroller.core.module.IFloodlightService;

import net.floodlightcontroller.core.IFloodlightProviderService;
import java.util.ArrayList;
import java.util.concurrent.ConcurrentSkipListSet;
import net.floodlightcontroller.packet.Ethernet;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.python.core.PyInstance;
import org.python.util.PythonInterpreter;


public class ARPHandler implements IOFMessageListener, IFloodlightModule {

    protected IFloodlightProviderService floodlightProvider;
    protected Set<Long> macAddresses;
    protected static Logger logger;

    // File where to find the mapping virtual IP to virtual MAC
    private String vnh_file = "/root/SWIFT/swift/main/virtual_nexthops";

    /**
     * This method performs the mapping Virtual IP to virtual MAC
     *
     * @param   ip      IP Address. If virtual there should be mapping.
     * @return  long    Virtual MAC that maps the vritual IP Address.
     */
    private long IPToMAC(String ip)
    {
        try
        {
            BufferedReader br = new BufferedReader(new FileReader(vnh_file));
            String line;
            String[] linetab;
            while ((line = br.readLine()) != null) {
                linetab = line.split("\t");
                if (linetab[0].equals(ip))
                    return Long.parseLong(linetab[1],10);
            }
            br.close();
            return 0;
        } catch (IOException e) {}
        return 0;
    }

    @Override
    public String getName() {
        return ARPHandler.class.getSimpleName();
    }

	@Override
	public boolean isCallbackOrderingPrereq(OFType type, String name) {
		// TODO Auto-generated method stub
		return false;
	}

	@Override
	public boolean isCallbackOrderingPostreq(OFType type, String name) {
		// TODO Auto-generated method stub
		return false;
	}

	@Override
	public Collection<Class<? extends IFloodlightService>> getModuleServices() {
		// TODO Auto-generated method stub
		return null;
	}

	@Override
	public Map<Class<? extends IFloodlightService>, IFloodlightService> getServiceImpls() {
		// TODO Auto-generated method stub
		return null;
	}

    @Override
    public Collection<Class<? extends IFloodlightService>> getModuleDependencies() {
        Collection<Class<? extends IFloodlightService>> l =
            new ArrayList<Class<? extends IFloodlightService>>();
        l.add(IFloodlightProviderService.class);
        return l;
    }

    @Override
    public void init(FloodlightModuleContext context) throws FloodlightModuleException {
        floodlightProvider = context.getServiceImpl(IFloodlightProviderService.class);
        macAddresses = new ConcurrentSkipListSet<Long>();
        logger = LoggerFactory.getLogger(ARPHandler.class);
    }


    @Override
    public void startUp(FloodlightModuleContext context) {
        logger.info ("Starting ARP handler module !");
        floodlightProvider.addOFMessageListener(OFType.PACKET_IN, this);
    }

	@Override
    public net.floodlightcontroller.core.IListener.Command receive( IOFSwitch sw, OFMessage msg, FloodlightContext cntx)
    {
        switch (msg.getType()) {
            case PACKET_IN:
                return this.processPacketInMessage(sw, (OFPacketIn) msg, cntx);
            default:
                break;
        }
        return Command.CONTINUE;
    }

    /**
    * Handles packetIn messages and decides what to do with it.
    *
    * @param sw The switch the packet is received.
    * @param piMsg The OpenFlow PacketIN message from the switch containing all relevant information.
    *
    * @return <b>Command</b> The command whether another listener should proceed or not.
    */
    protected Command processPacketInMessage(IOFSwitch sw, OFPacketIn piMsg, FloodlightContext cntx) {
        /* Get the Ethernet frame representation of the PacketIn message. */
        Ethernet ethPacket = IFloodlightProviderService.bcStore.get(cntx, IFloodlightProviderService.CONTEXT_PI_PAYLOAD);
        // If this is not an ARP message, continue.
        if (ethPacket.getEtherType().getValue() != Ethernet.TYPE_ARP )
            return Command.CONTINUE;

        /* A new empty ARP packet. */
        ARP arp = new ARP();
        // Get the ARP packet or continue.
        if (ethPacket.getPayload() instanceof ARP) {
            arp = (ARP) ethPacket.getPayload();
        } else {
            return Command.CONTINUE;
        }

        // Handle ARP request.
        if (arp.getOpCode() == ARP.OP_REQUEST) {
            logger.info ("Received ARP request in switch "+sw.getId()+" by port "+piMsg.getInPort());
            return this.handleARPRequest(arp, sw, piMsg.getInPort(), cntx);
        }

        return Command.CONTINUE;
    }

    /**
    * Handles incoming ARP requests. Reads the relevant information, creates an ARPRequest
    * object, sends out the ARP request message or, if the information is already known by
    * the system, sends back an ARP reply message.
    *
    * @param arp The ARP (request) packet received.
    * @param switchId The ID of the incoming switch where the ARP message is received.
    * @param portId The Port ID where the ARP message is received.
    * @return <b>Command</b> The command whether another listener should proceed or not.
    */
    protected Command handleARPRequest(ARP arp, IOFSwitch sw, OFPort portId, FloodlightContext cntx) {
        /* The known IP address of the ARP source. */
        long sourceIPAddress = IPv4.toIPv4Address(arp.getSenderProtocolAddress());
        /* The known MAC address of the ARP source. */
        long sourceMACAddress = Ethernet.toLong(arp.getSenderHardwareAddress());
        /* The IP address of the (yet unknown) ARP target. */
        long targetIPAddress = IPv4.toIPv4Address(arp.getTargetProtocolAddress());
        /* The MAC address of the (yet unknown) ARP target. */
        long targetMACAddress = 0;

        logger.info("Received ARP request message from " + arp.getSenderHardwareAddress() + " at " + sw.getId() + " - " + portId.getShortPortNumber() + " for target: " + IPv4.fromIPv4Address(IPv4.toIPv4Address(arp.getTargetProtocolAddress())));

        /* We compute the virtual MAC address for the targeted IP address, if the mapping exist */
        long virtual_mac = IPToMAC (IPv4.fromIPv4Address((int)targetIPAddress));

        /* If a mapping is found */
        if (virtual_mac != 0)
        {
            logger.info("Mapping done "+IPv4.fromIPv4Address((int)targetIPAddress)+"-->"+virtual_mac);

            /* Create an ARP reply frame (from target (source) to source (destination)). */
            IPacket arpReply = new Ethernet()
            .setSourceMACAddress(Ethernet.toByteArray(targetMACAddress))
            .setDestinationMACAddress(Ethernet.toByteArray(sourceMACAddress))
            .setEtherType(EthType.ARP)
            .setPayload(new ARP()
                .setHardwareType(ARP.HW_TYPE_ETHERNET)
                .setProtocolType(ARP.PROTO_TYPE_IP)
                .setOpCode(ARP.OP_REPLY)
                .setHardwareAddressLength((byte)6)
                .setProtocolAddressLength((byte)4)
                .setSenderHardwareAddress(Ethernet.toByteArray(virtual_mac))  /* Setting the virtual MAC */
                .setSenderProtocolAddress(IPv4.toIPv4AddressBytes((int)targetIPAddress))
                .setTargetHardwareAddress(Ethernet.toByteArray(sourceMACAddress))
                .setTargetProtocolAddress(IPv4.toIPv4AddressBytes((int)sourceIPAddress))
                .setPayload(new Data(new byte[] {0x01})));

            /* Send ARP reply */
            pushPacket(arpReply, sw, OFBufferId.NO_BUFFER, OFPort.ANY, portId, cntx, true);

            logger.info("Send ARP reply to " + sw.getId().getLong() + " at port " + portId);
        }
        else
            logger.info("NO Mapping for "+IPv4.fromIPv4Address((int)targetIPAddress));

        return Command.CONTINUE;

    }

	/**
     * used to push any packet - borrowed routine from Forwarding
     *
     * @param OFPacketIn pi
     * @param IOFSwitch sw
     * @param int bufferId
     * @param short inPort
     * @param short outPort
     * @param FloodlightContext cntx
     * @param boolean flush
     */
    public void pushPacket(IPacket packet,
                           IOFSwitch sw,
                           OFBufferId bufferId,
                           OFPort inPort,
                           OFPort outPort,
                           FloodlightContext cntx,
                           boolean flush) {

        logger.info("PacketOut srcSwitch={} inPort={} outPort={}", new Object[] {sw, inPort, outPort});

        OFPacketOut.Builder pob = sw.getOFFactory().buildPacketOut();

        // set actions
        List<OFAction> actions = new ArrayList<OFAction>();
        actions.add(sw.getOFFactory().actions().buildOutput().setPort(outPort).setMaxLen(Integer.MAX_VALUE).build());

        pob.setActions(actions);

        // set buffer_id, in_port
        pob.setBufferId(bufferId);
        pob.setInPort(inPort);

        byte[] packetData = packet.serialize();
        pob.setData(packetData);


        sw.write(pob.build());
    }

}
